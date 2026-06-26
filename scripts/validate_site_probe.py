#!/usr/bin/env python3
"""Small feasibility probe for authorized website mirroring.

The probe intentionally limits scope. It reads robots and sitemap, fetches a few
same-domain pages, downloads a few small assets, and optionally checks model APIs
through environment variables.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html.parser
import json
import os
import re
import sqlite3
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "site_mirror_agent.db"
OUT_DIR = ROOT / "output" / "site_probe"
USER_AGENT = "site-mirror-agent-probe/0.1"
TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}
TEXT_TAGS = {"title", "h1", "h2", "h3", "p", "a", "button", "span", "li"}
SKIP_TEXT_TAGS = {"script", "style", "noscript", "code", "pre", "svg"}


@dataclass
class PageProbe:
    url: str
    status_code: int | None = None
    content_hash: str | None = None
    title: str = ""
    internal_links: set[str] = field(default_factory=set)
    external_links: set[str] = field(default_factory=set)
    assets: set[str] = field(default_factory=set)
    text_samples: list[str] = field(default_factory=list)


class ProbeParser(html.parser.HTMLParser):
    def __init__(self, base_url: str, same_domain: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.same_domain = same_domain
        self.page = PageProbe(url=base_url)
        self._tag_stack: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag == "title":
            self._in_title = True

        attrs_dict = {k.lower(): v for k, v in attrs if v}
        for key in ("href", "src", "poster"):
            value = attrs_dict.get(key)
            if value:
                self._handle_url(value, is_link=(key == "href"))

        srcset = attrs_dict.get("srcset")
        if srcset:
            for item in srcset.split(","):
                candidate = item.strip().split(" ")[0]
                if candidate:
                    self._handle_url(candidate, is_link=False)

        style = attrs_dict.get("style")
        if style:
            for match in re.findall(r"url\(['\"]?([^)'\"\s]+)", style):
                self._handle_url(match, is_link=False)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.page.title = text[:200]
        current = self._tag_stack[-1] if self._tag_stack else ""
        if current in SKIP_TEXT_TAGS:
            return
        if current in TEXT_TAGS and len(self.page.text_samples) < 20 and has_english(text):
            self.page.text_samples.append(text[:240])

    def _handle_url(self, value: str, is_link: bool) -> None:
        if value.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            return
        absolute = normalize_url(urllib.parse.urljoin(self.base_url, value))
        if not absolute:
            return
        parsed = urllib.parse.urlparse(absolute)
        if is_link:
            if is_same_domain(parsed.hostname or "", self.same_domain):
                self.page.internal_links.add(absolute)
            else:
                self.page.external_links.add(absolute)
            return
        self.page.assets.add(absolute)


def has_english(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{3,}", text))


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [
        (key, value)
        for key, value in query
        if key not in TRACKING_PARAMS and not key.startswith("utm_")
    ]
    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            urllib.parse.urlencode(query),
            "",
        )
    )


def registrable_domain(hostname: str) -> str:
    parts = hostname.lower().split(".")
    if len(parts) <= 2:
        return hostname.lower()
    return ".".join(parts[-2:])


def is_same_domain(hostname: str, domain: str) -> bool:
    hostname = hostname.lower()
    return hostname == domain or hostname.endswith("." + domain)


def request_url(url: str, method: str = "GET", timeout: int = 20) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        headers = {k.lower(): v for k, v in response.headers.items()}
        body = b"" if method == "HEAD" else response.read()
        return response.status, headers, body


def fetch_text(url: str) -> str:
    _, headers, body = request_url(url)
    charset = "utf-8"
    content_type = headers.get("content-type", "")
    match = re.search(r"charset=([^;]+)", content_type)
    if match:
        charset = match.group(1)
    return body.decode(charset, errors="replace")


def sitemap_urls(sitemap_url: str, same_domain: str, limit: int) -> list[str]:
    try:
        xml_text = fetch_text(sitemap_url)
    except Exception:
        return []
    root = ET.fromstring(xml_text)
    urls: list[str] = []
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for loc in root.findall(".//sm:loc", namespace):
        if loc.text:
            normalized = normalize_url(loc.text.strip())
            host = urllib.parse.urlparse(normalized).hostname or ""
            if normalized and is_same_domain(host, same_domain):
                urls.append(normalized)
        if len(urls) >= limit:
            break
    return urls


def probe_page(url: str, same_domain: str) -> tuple[PageProbe, bytes]:
    page = PageProbe(url=url)
    try:
        status, _, body = request_url(url)
    except urllib.error.HTTPError as exc:
        page.status_code = exc.code
        return page, b""
    page.status_code = status
    page.content_hash = hashlib.sha256(body).hexdigest()
    parser = ProbeParser(url, same_domain)
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.page.status_code = page.status_code
    parser.page.content_hash = page.content_hash
    return parser.page, body


def download_assets(run_id: int, pages: list[PageProbe], limit: int) -> list[dict[str, Any]]:
    asset_dir = OUT_DIR / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in pages:
        for asset_url in sorted(page.assets):
            if len(saved) >= limit:
                return saved
            if asset_url in seen:
                continue
            seen.add(asset_url)
            record = {
                "run_id": run_id,
                "page_url": page.url,
                "asset_url": asset_url,
                "local_path": None,
                "content_type": None,
                "size_bytes": None,
                "status": "skipped",
            }
            try:
                status, headers, body = request_url(asset_url, timeout=25)
                content_type = headers.get("content-type", "").split(";")[0]
                if status != 200:
                    record["status"] = f"http_{status}"
                elif len(body) > 2_000_000:
                    record["status"] = "too_large"
                else:
                    suffix = suffix_for(asset_url, content_type)
                    asset_hash = hashlib.sha256(body).hexdigest()
                    path = asset_dir / f"{asset_hash[:24]}{suffix}"
                    path.write_bytes(body)
                    record.update(
                        {
                            "local_path": str(path),
                            "content_type": content_type,
                            "size_bytes": len(body),
                            "status": "saved",
                        }
                    )
            except Exception as exc:
                record["status"] = f"error:{type(exc).__name__}"
            saved.append(record)
            time.sleep(0.2)
    return saved


def suffix_for(url: str, content_type: str) -> str:
    path_suffix = Path(urllib.parse.urlparse(url).path).suffix
    if path_suffix and len(path_suffix) <= 8:
        return path_suffix
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "text/css": ".css",
        "application/javascript": ".js",
        "text/javascript": ".js",
        "font/woff2": ".woff2",
        "video/mp4": ".mp4",
    }
    return mapping.get(content_type, ".bin")


def translation_api_check(sample: str) -> dict[str, Any]:
    base_url = os.getenv("ANTHROPIC_API_URL") or os.getenv("ANTHROPIC_API_url")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("TRANSLATION_MODEL", "glm-5.1")
    if not base_url or not api_key:
        return {"status": "skipped", "reason": "missing_env"}

    endpoint = base_url.rstrip("/") + "/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 300,
        "messages": [
            {
                "role": "user",
                "content": (
                    "将下面网页文案翻译成简体中文，只输出译文，保持品牌名不变：\n"
                    + sample
                ),
            }
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    try:
        status, _, body = post_json(endpoint, payload, headers)
        data = json.loads(body.decode("utf-8", errors="replace"))
        text = extract_message_text(data)
        return {"status": "ok", "http_status": status, "model": model, "sample_output": text[:300]}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__, "message": str(exc)[:300]}


def vision_check() -> dict[str, Any]:
    base_url = os.getenv("VISION_API_URL") or os.getenv("vision_url")
    api_key = os.getenv("VISION_API_KEY")
    model = os.getenv("VISION_MODEL", "doubao-seed-1-6-flash-250828")
    if not base_url or not api_key:
        return {"status": "skipped", "reason": "missing_env"}

    endpoint = base_url.rstrip("/") + "/chat/completions"
    test_png = base64.b64encode(make_test_png(16, 16)).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "判断这张测试图是否可见，只回答可见或不可见。"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{test_png}"},
                    },
                ],
            }
        ],
        "max_tokens": 20,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    try:
        status, _, body = post_json(endpoint, payload, headers)
        data = json.loads(body.decode("utf-8", errors="replace"))
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"status": "ok", "http_status": status, "model": model, "sample_output": content[:120]}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__, "message": str(exc)[:300]}


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=40, context=context) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        raise RuntimeError(f"HTTP {exc.code}: {body.decode('utf-8', errors='replace')[:500]}") from exc


def make_test_png(width: int, height: int) -> bytes:
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def extract_message_text(data: dict[str, Any]) -> str:
    content = data.get("content", [])
    if isinstance(content, list):
        parts = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "\n".join(part for part in parts if part)
    if isinstance(content, str):
        return content
    return json.dumps(data, ensure_ascii=False)[:300]


def insert_run(target_url: str, same_domain: str, summary: dict[str, Any]) -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        status = "ok" if summary.get("pages") else "partial"
        cursor = conn.execute(
            """
            INSERT INTO validation_runs
                (target_url, same_domain, status, summary_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                target_url,
                same_domain,
                status,
                json.dumps(summary, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return int(cursor.lastrowid)


def insert_details(run_id: int, pages: list[PageProbe], assets: list[dict[str, Any]]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        for page in pages:
            conn.execute(
                """
                INSERT INTO validation_pages
                    (run_id, url, status_code, content_hash, title, internal_links,
                     external_links, assets, text_samples)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    page.url,
                    page.status_code,
                    page.content_hash,
                    page.title,
                    len(page.internal_links),
                    len(page.external_links),
                    len(page.assets),
                    len(page.text_samples),
                ),
            )
        for asset in assets:
            conn.execute(
                """
                INSERT INTO validation_assets
                    (run_id, page_url, asset_url, local_path, content_type,
                     size_bytes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    asset["page_url"],
                    asset["asset_url"],
                    asset["local_path"],
                    asset["content_type"],
                    asset["size_bytes"],
                    asset["status"],
                ),
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--max-assets", type=int, default=5)
    parser.add_argument("--with-models", action="store_true")
    args = parser.parse_args()

    start_url = normalize_url(args.url)
    if not start_url:
        print("Invalid URL", file=sys.stderr)
        return 2
    host = urllib.parse.urlparse(start_url).hostname or ""
    same_domain = registrable_domain(host)
    sitemap_url = urllib.parse.urlunparse(("https", host, "/sitemap.xml", "", "", ""))
    robots_url = urllib.parse.urlunparse(("https", host, "/robots.txt", "", "", ""))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    robots_text = fetch_text(robots_url)
    candidate_urls = sitemap_urls(sitemap_url, same_domain, args.max_pages)
    if start_url not in candidate_urls:
        candidate_urls.insert(0, start_url)
    candidate_urls = candidate_urls[: args.max_pages]

    pages: list[PageProbe] = []
    for url in candidate_urls:
        page, body = probe_page(url, same_domain)
        pages.append(page)
        if body:
            page_path = OUT_DIR / f"page_{len(pages)}.html"
            page_path.write_bytes(body)
        time.sleep(0.4)

    summary: dict[str, Any] = {
        "robots_allows_all": "Allow: /" in robots_text,
        "sitemap_url": sitemap_url,
        "sitemap_candidates": len(candidate_urls),
        "pages": [
            {
                "url": page.url,
                "status_code": page.status_code,
                "title": page.title,
                "internal_links": len(page.internal_links),
                "external_links": len(page.external_links),
                "assets": len(page.assets),
                "text_samples": page.text_samples[:3],
            }
            for page in pages
        ],
    }
    run_id = insert_run(start_url, same_domain, summary)
    assets = download_assets(run_id, pages, args.max_assets)

    if args.with_models:
        sample = next((sample for page in pages for sample in page.text_samples), "Example product overview")
        summary["translation_check"] = translation_api_check(sample)
        summary["vision_check"] = vision_check()

    summary["assets_saved"] = sum(1 for asset in assets if asset["status"] == "saved")
    summary["run_id"] = run_id
    insert_details(run_id, pages, assets)

    report_path = OUT_DIR / f"validation_run_{run_id}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
