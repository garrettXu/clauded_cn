#!/usr/bin/env python3
"""Translate replicated static mirrors into locale-specific static mirrors."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Comment, Declaration, Doctype, NavigableString, ProcessingInstruction, Tag


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARENT_TAGS = {"script", "style", "code", "pre", "textarea", "noscript", "template", "svg"}
TEXT_ATTRS = {"alt", "title", "aria-label", "placeholder"}
META_CONTENT_KEYS = {
    "description",
    "og:title",
    "og:description",
    "twitter:title",
    "twitter:description",
}
URL_RE = re.compile(r"^(https?:)?//|^[a-z][a-z0-9+.-]*:", re.I)
EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)
HAS_WORD_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]")


@dataclasses.dataclass
class Segment:
    segment_id: str
    page_host: str
    page_path: str
    source: str
    kind: str
    selector: str
    attr: str | None = None


@dataclasses.dataclass
class PageResult:
    host: str
    page_path: str
    status: str
    source_file: str
    output_file: str
    segments_total: int = 0
    segments_translated: int = 0
    segments_cache_hit: int = 0
    segments_skipped: int = 0
    error: str | None = None


class TranslationError(RuntimeError):
    pass


class TranslationCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: dict[str, dict[str, Any]] = {}
        if path.exists():
            self.items = json.loads(path.read_text(encoding="utf-8"))

    def key(
        self,
        source: str,
        source_language: str,
        target_language: str,
        model: str,
        style_profile: str,
    ) -> str:
        raw = "\n".join([source, source_language, target_language, model, style_profile])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        item = self.items.get(key)
        if not item:
            return None
        return str(item.get("target") or "")

    def set(
        self,
        key: str,
        source: str,
        target: str,
        source_language: str,
        target_language: str,
        model: str,
        style_profile: str,
        status: str,
    ) -> None:
        self.items[key] = {
            "source": source,
            "target": target,
            "source_language": source_language,
            "target_language": target_language,
            "model": model,
            "style_profile": style_profile,
            "status": status,
            "locked": False,
            "updated_at": now_iso(),
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")


class Translator:
    def __init__(
        self,
        target_language: str,
        source_language: str,
        model: str,
        dry_run: bool,
        api_url: str | None,
        api_key: str | None,
        max_retries: int,
    ) -> None:
        self.target_language = target_language
        self.source_language = source_language
        self.model = model
        self.dry_run = dry_run
        self.api_url = api_url
        self.api_key = api_key
        self.max_retries = max_retries

    def translate_many(self, items: list[Segment]) -> dict[str, str]:
        if not items:
            return {}
        if self.dry_run:
            return {item.segment_id: self.pseudo_translate(item.source) for item in items}
        if not self.api_url or not self.api_key:
            raise TranslationError("missing TRANSLATION_API_URL/TRANSLATION_API_KEY or ANTHROPIC_API_URL/ANTHROPIC_API_KEY")
        return self.remote_translate_many(items)

    def pseudo_translate(self, text: str) -> str:
        return f"[{self.target_language}] {text}"

    def remote_translate_many(self, items: list[Segment]) -> dict[str, str]:
        prompt_items = [{"id": item.segment_id, "text": item.source} for item in items]
        prompt = (
            "Translate the following website UI text segments.\n"
            f"Source language: {self.source_language}\n"
            f"Target language: {self.target_language}\n"
            "Rules: keep brand names, URLs, emails, code, variables, numbers, and placeholders unchanged. "
            "Use concise UI copy for navigation and buttons. Return only valid JSON in this shape: "
            '{"translations":[{"id":"...","target":"..."}]}.\n\n'
            + json.dumps({"segments": prompt_items}, ensure_ascii=False)
        )
        for attempt in range(1, self.max_retries + 1):
            try:
                content = self.call_model(prompt)
                return parse_translation_json(content, {item.segment_id for item in items})
            except Exception as exc:
                if attempt >= self.max_retries:
                    raise TranslationError(str(exc)) from exc
                time.sleep(min(2 * attempt, 6))
        return {}

    def call_model(self, prompt: str) -> str:
        assert self.api_url and self.api_key
        if "/anthropic" in self.api_url:
            endpoint = self.api_url.rstrip("/") + "/v1/messages"
            payload = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
            data = post_json(endpoint, payload, headers)
            return extract_anthropic_text(data)

        endpoint = self.api_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise website localization engine. Return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        data = post_json(endpoint, payload, headers)
        return str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))


class TranslationAgent:
    def __init__(self, args: argparse.Namespace) -> None:
        self.input_root = Path(args.input_root).resolve()
        self.output_root = Path(args.output_root).resolve() if args.output_root else self.input_root.parent / args.locale
        self.locale = args.locale
        self.source_language = args.source_language
        self.model = args.model
        self.style_profile = args.style_profile
        self.max_pages = args.max_pages
        self.batch_size_chars = args.batch_size_chars
        self.port_offset = args.port_offset
        self.overwrite = args.overwrite
        self.dry_run = args.dry_run
        self.created_at = now_iso()
        self.cache = TranslationCache(self.output_root / "cache" / "translation_cache.json")
        self.port_map: dict[str, str] = {}
        self.segment_index: list[dict[str, Any]] = []
        self.page_results: list[PageResult] = []
        self.errors: list[dict[str, Any]] = []
        self.translator = Translator(
            target_language=self.locale,
            source_language=self.source_language,
            model=self.model,
            dry_run=self.dry_run,
            api_url=args.api_url,
            api_key=args.api_key,
            max_retries=args.max_retries,
        )

    def run(self) -> int:
        self.validate_roots()
        manifest = self.read_json(self.input_root / "manifest.json")
        self.prepare_output(manifest)
        pages = self.find_pages(manifest)
        if self.max_pages:
            pages = pages[: self.max_pages]
        for page in pages:
            self.process_page(page)
        self.cache.save()
        self.write_segment_index()
        self.write_manifest(manifest)
        self.write_reports()
        self.write_deployment(manifest)
        return 1 if self.errors else 0

    def validate_roots(self) -> None:
        if not self.input_root.exists():
            raise SystemExit(f"Input root does not exist: {self.input_root}")
        if not (self.input_root / "hosts").exists():
            raise SystemExit(f"Input root is missing hosts/: {self.input_root}")
        if self.output_root == self.input_root or self.output_root.is_relative_to(self.input_root):
            raise SystemExit("Output root must not be the same as, or inside, input_root.")
        if self.output_root.exists() and not self.overwrite:
            raise SystemExit(f"Output root already exists. Use --overwrite to update it: {self.output_root}")

    def prepare_output(self, manifest: dict[str, Any]) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        for dirname in ["reports", "cache", "glossary", "nginx", "snapshots/screenshots"]:
            (self.output_root / dirname).mkdir(parents=True, exist_ok=True)
        for host in manifest.get("hosts", []):
            source_host = host.get("source_host")
            if not source_host:
                continue
            if "local_port" in host:
                old_port = str(host["local_port"])
                self.port_map[f"http://localhost:{old_port}"] = f"http://localhost:{int(old_port) + self.port_offset}"
            local_preview_root = self.input_root / str(host.get("local_preview_root", ""))
            source_site_root = self.input_root / str(host.get("site_root", f"hosts/{source_host}/site"))
            source_site = local_preview_root if local_preview_root.exists() else source_site_root
            target_site = self.output_root / "hosts" / source_host / "site"
            if not source_site.exists():
                continue
            shutil.copytree(source_site, target_site, dirs_exist_ok=True)
            self.write_locale_css(target_site)

    def find_pages(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for page in manifest.get("pages", []):
            output_path = page.get("deploy_path") or page.get("local_path")
            source_path = page.get("local_preview_path") or output_path
            if not output_path or not source_path:
                continue
            source_file = self.input_root / source_path
            if source_file.suffix.lower() not in {".html", ".htm"} or not source_file.exists():
                continue
            if source_file in seen:
                continue
            seen.add(source_file)
            page["_translation_source_path"] = str(source_path)
            page["_translation_output_path"] = str(output_path)
            pages.append(page)
        if pages:
            return pages
        for source_file in sorted((self.input_root / "hosts").glob("*/site/**/*.html")):
            source_host = source_file.relative_to(self.input_root / "hosts").parts[0]
            rel = source_file.relative_to(self.input_root / "hosts" / source_host / "site")
            pages.append(
                {
                    "source_host": source_host,
                    "source_path": "/" + rel.as_posix(),
                    "deploy_path": f"hosts/{source_host}/site/{rel.as_posix()}",
                    "url": "",
                }
            )
        return pages

    def process_page(self, page: dict[str, Any]) -> None:
        source_host = str(page["source_host"])
        source_path = str(page.get("_translation_source_path") or page.get("local_preview_path") or page.get("deploy_path") or page.get("local_path"))
        output_path = str(page.get("_translation_output_path") or page.get("deploy_path") or page.get("local_path"))
        source_file = self.input_root / source_path
        output_file = self.output_root / output_path
        result = PageResult(
            host=source_host,
            page_path=str(page.get("source_path") or deploy_path),
            status="pending",
            source_file=str(source_file.relative_to(ROOT) if source_file.is_relative_to(ROOT) else source_file),
            output_file=str(output_file.relative_to(ROOT) if output_file.is_relative_to(ROOT) else output_file),
        )
        try:
            html = self.rewrite_preview_ports(output_file.read_text(encoding="utf-8", errors="replace"))
            soup = BeautifulSoup(html, "html5lib")
            site_root = self.output_root / "hosts" / source_host / "site"
            self.inject_lang_and_css(soup, output_file, site_root)
            segments = self.extract_segments(soup, source_host, result.page_path)
            result.segments_total = len(segments)
            translated, cache_hits = self.translate_segments(segments)
            result.segments_cache_hit = cache_hits
            result.segments_translated = len(translated) - cache_hits
            self.apply_translations(soup, source_host, result.page_path, translated)
            output_file.write_text(str(soup), encoding="utf-8")
            result.status = "translated"
        except Exception as exc:
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"
            self.errors.append(dataclasses.asdict(result))
        self.page_results.append(result)

    def extract_segments(self, soup: BeautifulSoup, host: str, page_path: str) -> list[Segment]:
        segments: list[Segment] = []
        for text_node in list(soup.find_all(string=True)):
            if not isinstance(text_node, NavigableString):
                continue
            if should_skip_text_node(text_node):
                continue
            source = str(text_node).strip()
            selector = css_path(text_node.parent) if isinstance(text_node.parent, Tag) else ""
            segments.append(make_segment(host, page_path, source, "text", selector, None))

        for tag in soup.find_all(True):
            if tag.name in SKIP_PARENT_TAGS:
                continue
            for attr in TEXT_ATTRS:
                value = tag.get(attr)
                if isinstance(value, str) and is_translatable_text(value):
                    segments.append(make_segment(host, page_path, value.strip(), "attr", css_path(tag), attr))
            if tag.name == "meta":
                key = str(tag.get("name") or tag.get("property") or "").lower()
                value = tag.get("content")
                if key in META_CONTENT_KEYS and isinstance(value, str) and is_translatable_text(value):
                    segments.append(make_segment(host, page_path, value.strip(), "attr", css_path(tag), "content"))

        unique: dict[str, Segment] = {}
        for segment in segments:
            unique[segment.segment_id] = segment
        return list(unique.values())

    def rewrite_preview_ports(self, html: str) -> str:
        for old, new in self.port_map.items():
            html = html.replace(old, new)
        return html

    def translate_segments(self, segments: list[Segment]) -> tuple[dict[str, str], int]:
        translated: dict[str, str] = {}
        cache_hits = 0
        pending: list[Segment] = []
        pending_chars = 0
        for segment in segments:
            key = self.cache.key(segment.source, self.source_language, self.locale, self.model, self.style_profile)
            cached = self.cache.get(key)
            if cached:
                translated[segment.segment_id] = cached
                cache_hits += 1
                continue
            if pending and pending_chars + len(segment.source) > self.batch_size_chars:
                translated.update(self.flush_batch(pending))
                pending = []
                pending_chars = 0
            pending.append(segment)
            pending_chars += len(segment.source)
        if pending:
            translated.update(self.flush_batch(pending))
        return translated, cache_hits

    def flush_batch(self, segments: list[Segment]) -> dict[str, str]:
        result = self.translator.translate_many(segments)
        for segment in segments:
            target = result.get(segment.segment_id)
            if not target:
                continue
            key = self.cache.key(segment.source, self.source_language, self.locale, self.model, self.style_profile)
            self.cache.set(
                key,
                segment.source,
                target,
                self.source_language,
                self.locale,
                self.model,
                self.style_profile,
                "dry_run" if self.dry_run else "machine_translated",
            )
            self.segment_index.append(
                {
                    "segment_id": segment.segment_id,
                    "host": segment.page_host,
                    "page_path": segment.page_path,
                    "kind": segment.kind,
                    "selector": segment.selector,
                    "attr": segment.attr,
                    "source": segment.source,
                    "target": target,
                }
            )
        return result

    def apply_translations(
        self,
        soup: BeautifulSoup,
        host: str,
        page_path: str,
        translated: dict[str, str],
    ) -> None:
        for text_node in list(soup.find_all(string=True)):
            if not isinstance(text_node, NavigableString) or should_skip_text_node(text_node):
                continue
            source = str(text_node).strip()
            selector = css_path(text_node.parent) if isinstance(text_node.parent, Tag) else ""
            segment = make_segment(host, page_path, source, "text", selector, None)
            target = translated.get(segment.segment_id)
            if target:
                text_node.replace_with(preserve_edge_whitespace(str(text_node), target))

        for tag in soup.find_all(True):
            if tag.name in SKIP_PARENT_TAGS:
                continue
            for attr in TEXT_ATTRS:
                value = tag.get(attr)
                if isinstance(value, str) and is_translatable_text(value):
                    segment = make_segment(host, page_path, value.strip(), "attr", css_path(tag), attr)
                    target = translated.get(segment.segment_id)
                    if target:
                        tag[attr] = target
            if tag.name == "meta":
                key = str(tag.get("name") or tag.get("property") or "").lower()
                value = tag.get("content")
                if key in META_CONTENT_KEYS and isinstance(value, str) and is_translatable_text(value):
                    segment = make_segment(host, page_path, value.strip(), "attr", css_path(tag), "content")
                    target = translated.get(segment.segment_id)
                    if target:
                        tag["content"] = target

    def inject_lang_and_css(self, soup: BeautifulSoup, output_file: Path, site_root: Path) -> None:
        html_tag = soup.find("html")
        if isinstance(html_tag, Tag):
            html_tag["lang"] = self.locale
        head = soup.find("head")
        if not isinstance(head, Tag):
            return
        href = relative_url(output_file.parent, site_root / "__locale" / "locale-layout.css")
        existing = head.find("link", attrs={"data-locale-agent": "layout"})
        if isinstance(existing, Tag):
            existing["href"] = href
            return
        link = soup.new_tag("link", rel="stylesheet", href=href)
        link["data-locale-agent"] = "layout"
        head.append(link)

    def write_locale_css(self, site_root: Path) -> None:
        target = site_root / "__locale" / "locale-layout.css"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(locale_css(self.locale), encoding="utf-8")

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        translated = json.loads(json.dumps(manifest))
        translated["locale"] = self.locale
        translated["source_root"] = str(self.input_root)
        translated["created_at"] = self.created_at
        for host in translated.get("hosts", []):
            if "local_port" in host:
                host["source_local_port"] = host["local_port"]
                host["local_port"] = int(host["local_port"]) + self.port_offset
            source_host = host.get("source_host")
            if source_host:
                host["site_root"] = f"hosts/{source_host}/site"
                host["local_preview_root"] = f"hosts/{source_host}/site"
        for page in translated.get("pages", []):
            page.pop("_translation_source_path", None)
            page.pop("_translation_output_path", None)
            host_port = None
            for host in translated.get("hosts", []):
                if host.get("source_host") == page.get("source_host"):
                    host_port = host.get("local_port")
                    break
            if host_port and page.get("source_path"):
                page["local_preview_url"] = f"http://localhost:{host_port}{page['source_path']}"
            if page.get("deploy_path"):
                page["local_preview_path"] = page["deploy_path"]
        (self.output_root / "manifest.json").write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_reports(self) -> None:
        reports_dir = self.output_root / "reports"
        pages_total = len(self.page_results)
        pages_translated = sum(1 for item in self.page_results if item.status == "translated")
        segments_total = sum(item.segments_total for item in self.page_results)
        segments_cache_hit = sum(item.segments_cache_hit for item in self.page_results)
        segments_translated = sum(item.segments_translated for item in self.page_results)
        report = {
            "site_id": self.read_json(self.input_root / "manifest.json").get("site_id"),
            "locale": self.locale,
            "run_id": "translate_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
            "dry_run": self.dry_run,
            "created_at": self.created_at,
            "pages_total": pages_total,
            "pages_translated": pages_translated,
            "pages_failed": pages_total - pages_translated,
            "segments_total": segments_total,
            "segments_cache_hit": segments_cache_hit,
            "segments_model_translated": segments_translated,
            "segments_skipped": 0,
            "model": self.model,
            "pages": [dataclasses.asdict(item) for item in self.page_results],
        }
        (reports_dir / "translation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        layout_report = {
            "locale": self.locale,
            "pages_checked": 0,
            "issues_total": 0,
            "auto_fixed": 0,
            "needs_manual_review": 0,
            "status": "not_implemented_in_mvp",
        }
        visual_report = {
            "locale": self.locale,
            "screenshots_total": 0,
            "passed": 0,
            "failed": 0,
            "status": "not_implemented_in_mvp",
        }
        review_queue = {"items": self.errors}
        for name, data in [
            ("layout_report.json", layout_report),
            ("visual_report.json", visual_report),
            ("review_queue.json", review_queue),
        ]:
            (reports_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_segment_index(self) -> None:
        path = self.output_root / "cache" / "segment_index.json"
        path.write_text(json.dumps({"segments": self.segment_index}, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_deployment(self, manifest: dict[str, Any]) -> None:
        lines = [
            f"# {self.locale} 翻译站部署说明",
            "",
            f"- 输入目录：`{self.input_root}`",
            f"- 输出目录：`{self.output_root}`",
            f"- 生成时间：`{self.created_at}`",
            f"- dry-run：`{self.dry_run}`",
            "",
            "## Host 映射",
            "",
            "| Host | 本地预览端口 | 静态目录 |",
            "| --- | --- | --- |",
        ]
        for host in manifest.get("hosts", []):
            source_host = host.get("source_host")
            if not source_host:
                continue
            port = int(host.get("local_port", 0)) + self.port_offset
            lines.append(f"| {source_host} | http://localhost:{port} | hosts/{source_host}/site |")
        lines += [
            "",
            "## 说明",
            "",
            "- 本产物为静态站点，不依赖数据库。",
            "- 资源随 `site` 目录复制，语言补丁位于 `site/__locale/locale-layout.css`。",
            "- `mirror/original` 不会被修改。",
        ]
        (self.output_root / "DEPLOYMENT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))


def make_segment(host: str, page_path: str, source: str, kind: str, selector: str, attr: str | None) -> Segment:
    raw = "\n".join([host, page_path, selector, attr or "", source])
    return Segment(
        segment_id=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        page_host=host,
        page_path=page_path,
        source=source,
        kind=kind,
        selector=selector,
        attr=attr,
    )


def should_skip_text_node(text_node: NavigableString) -> bool:
    if isinstance(text_node, (Comment, Declaration, Doctype, ProcessingInstruction)):
        return True
    parent = text_node.parent
    if not isinstance(parent, Tag) or parent.name in SKIP_PARENT_TAGS:
        return True
    return not is_translatable_text(str(text_node))


def is_translatable_text(text: str) -> bool:
    value = " ".join(text.split())
    if len(value) < 2:
        return False
    if URL_RE.search(value) or EMAIL_RE.search(value):
        return False
    if not HAS_WORD_RE.search(value):
        return False
    if value.startswith(("{", "[", "$", "./", "../", "/")):
        return False
    return True


def preserve_edge_whitespace(original: str, replacement: str) -> str:
    leading = original[: len(original) - len(original.lstrip())]
    trailing = original[len(original.rstrip()) :]
    return leading + replacement + trailing


def css_path(tag: Tag | None) -> str:
    if not isinstance(tag, Tag):
        return ""
    parts: list[str] = []
    current: Tag | None = tag
    while isinstance(current, Tag) and current.name != "[document]":
        if current.get("id"):
            parts.append(f"{current.name}#{current.get('id')}")
            break
        parent = current.parent
        index = 1
        if isinstance(parent, Tag):
            siblings = [child for child in parent.find_all(current.name, recursive=False)]
            if len(siblings) > 1:
                index = siblings.index(current) + 1
        part = current.name
        if index > 1:
            part += f":nth-of-type({index})"
        parts.append(part)
        current = parent if isinstance(parent, Tag) else None
    return " > ".join(reversed(parts))


def parse_translation_json(content: str, expected_ids: set[str]) -> dict[str, str]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    data = json.loads(raw)
    items = data.get("translations", data if isinstance(data, list) else [])
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        target = str(item.get("target") or "")
        if item_id in expected_ids and target:
            result[item_id] = target
    missing = expected_ids - set(result)
    if missing:
        raise TranslationError(f"model response missing {len(missing)} translations")
    return result


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=90, context=context) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise TranslationError(f"HTTP {exc.code}: {body[:500]}") from exc


def extract_anthropic_text(data: dict[str, Any]) -> str:
    content = data.get("content", [])
    if isinstance(content, list):
        return "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict)).strip()
    return str(content)


def locale_css(locale: str) -> str:
    return f"""html[lang="{locale}"] body {{
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  text-rendering: optimizeLegibility;
}}

html[lang="{locale}"] button,
html[lang="{locale}"] a,
html[lang="{locale}"] p,
html[lang="{locale}"] h1,
html[lang="{locale}"] h2,
html[lang="{locale}"] h3,
html[lang="{locale}"] li {{
  overflow-wrap: anywhere;
}}
"""


def relative_url(from_dir: Path, target: Path) -> str:
    return os.path.relpath(target, from_dir).replace(os.sep, "/")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate a replicated static mirror into a locale output directory.")
    parser.add_argument("input_root", help="Path to mirror/original.")
    parser.add_argument("--output-root", help="Output root. Defaults to sibling directory named by --locale.")
    parser.add_argument("--locale", default="zh-CN", help="Target locale directory and HTML lang value.")
    parser.add_argument("--source-language", default="en", help="Source language hint.")
    parser.add_argument("--model", default=os.getenv("TRANSLATION_MODEL", "glm-5.1"))
    parser.add_argument("--style-profile", default="concise_professional")
    parser.add_argument("--api-url", default=env_value("TRANSLATION_API_URL", "ANTHROPIC_API_URL", "ANTHROPIC_API_url"))
    parser.add_argument("--api-key", default=env_value("TRANSLATION_API_KEY", "ANTHROPIC_API_KEY"))
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--batch-size-chars", type=int, default=6000)
    parser.add_argument("--port-offset", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=0, help="Limit pages for validation.")
    parser.add_argument("--dry-run", action="store_true", help="Use pseudo translations without calling a model.")
    parser.add_argument("--overwrite", action="store_true", help="Allow updating an existing output root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return TranslationAgent(args).run()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"translation_agent error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
