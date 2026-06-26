from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from scripts.replication_agent import (
    CrawlPolicy,
    CrawlItem,
    DomainPolicy,
    ReplicationAgent,
    ReplicationConfig,
    ResourceItem,
    load_config,
)


def make_agent() -> ReplicationAgent:
    tmp = Path(tempfile.mkdtemp(prefix="replication_agent_test_", dir="/tmp"))
    config = ReplicationConfig(
        site_id="test",
        target_url="https://www.example.com/",
        out_dir=tmp,
        domain_policy=DomainPolicy(root_domain="example.com", include_subdomains=True),
    )
    return ReplicationAgent(config)


class ReplicationAgentTests(unittest.TestCase):
    def test_load_config_accepts_only_target_url(self) -> None:
        args = argparse.Namespace(
            url="https://www.example.com/",
            config=None,
            site_id=None,
            root_domain=None,
            out_dir=None,
            max_pages_per_host=None,
            max_assets_per_host=None,
            max_depth=None,
            timeout_seconds=None,
            port_start=None,
            force_refresh=False,
            render_dynamic_pages=False,
            require_browser_render=False,
            visual_compare=False,
            visual_sample_pages=None,
            no_robots=False,
            ack_authorized=True,
        )

        config = load_config(args)

        self.assertEqual(config.target_url, "https://www.example.com/")
        self.assertEqual(config.site_id, "example.com")
        self.assertEqual(config.domain_policy.root_domain, "example.com")
        self.assertIn("www.example.com", config.domain_policy.include)
        self.assertEqual(config.out_dir.name, "example.com")
        self.assertEqual(config.crawl_policy.max_pages_per_host, CrawlPolicy.max_pages_per_host)
        self.assertTrue(config.crawl_policy.render_dynamic_pages)
        self.assertEqual(config.crawl_policy.worker_count, CrawlPolicy.worker_count)
        self.assertTrue(config.authorization_policy.require_ack)
        self.assertTrue(config.authorization_policy.authorized)

    def test_load_config_accepts_minimal_config_file(self) -> None:
        config_file = Path(tempfile.mkdtemp(prefix="replication_config_test_", dir="/tmp")) / "site.json"
        config_file.write_text('{"target_url":"https://docs.example.com/"}', encoding="utf-8")
        args = argparse.Namespace(
            url=None,
            config=str(config_file),
            site_id=None,
            root_domain=None,
            out_dir=None,
            max_pages_per_host=None,
            max_assets_per_host=None,
            max_depth=None,
            timeout_seconds=None,
            port_start=None,
            force_refresh=False,
            render_dynamic_pages=False,
            require_browser_render=False,
            visual_compare=False,
            visual_sample_pages=None,
            no_robots=False,
            ack_authorized=True,
        )

        config = load_config(args)

        self.assertEqual(config.target_url, "https://docs.example.com/")
        self.assertEqual(config.domain_policy.root_domain, "example.com")
        self.assertIn("docs.example.com", config.domain_policy.include)
        self.assertEqual(config.out_dir.name, "example.com")

    def test_next_image_effective_asset_url(self) -> None:
        agent = make_agent()
        nested = "https%3A%2F%2Fcdn.example.com%2Fimage.png%3Fw%3D128"
        result = agent.effective_asset_url(
            f"https://www.example.com/_next/image?url={nested}&q=75",
            "https://www.example.com/page",
        )
        self.assertEqual(result, "https://cdn.example.com/image.png?w=128")

    def test_target_base_domain_maps_root_and_subdomains(self) -> None:
        agent = make_agent()
        agent.config.deployment.target_base_domain = "mirror.test"
        self.assertEqual(agent.deploy_host("example.com"), "mirror.test")
        self.assertEqual(agent.deploy_host("www.example.com"), "www.mirror.test")
        self.assertEqual(agent.deploy_host("docs.example.com"), "docs.mirror.test")

    def test_duplicate_ports_are_deduped(self) -> None:
        agent = make_agent()
        agent.register_host("www.example.com", 9000, None)
        second = agent.register_host("docs.example.com", 9000, None)
        self.assertEqual(second.local_port, 9001)

    def test_quality_report_blocks_failed_pages_and_missing_resources(self) -> None:
        agent = make_agent()
        agent.original_dir.mkdir(parents=True, exist_ok=True)
        agent.crawl_table = {
            "https://www.example.com/": CrawlItem(url="https://www.example.com/", host="www.example.com", depth=0, status="replicated"),
            "https://www.example.com/missing": CrawlItem(url="https://www.example.com/missing", host="www.example.com", depth=1, status="http_404", status_code=404),
            "https://www.example.com/slow": CrawlItem(url="https://www.example.com/slow", host="www.example.com", depth=1, status="fetch_failed"),
            "https://www.example.com/todo": CrawlItem(url="https://www.example.com/todo", host="www.example.com", depth=1, status="queued"),
        }
        agent.resource_table = {
            "https://www.example.com/app.css": ResourceItem(
                url="https://www.example.com/app.css",
                host="www.example.com",
                page_url="https://www.example.com/",
                public_path="/app.css",
                status="error",
            )
        }
        report = agent.compute_quality_report()
        self.assertFalse(report["ready_for_release"])
        self.assertEqual(report["page_counts"]["acceptable_terminal"], 1)
        self.assertEqual(report["page_counts"]["failed"], 1)
        self.assertEqual(report["page_counts"]["pending"], 1)
        self.assertEqual(report["resource_counts"]["failed"], 1)

    def test_missing_local_static_refs_are_repaired_from_other_hosts(self) -> None:
        agent = make_agent()
        agent.ensure_host("www.example.com")
        agent.ensure_host("docs.example.com")
        source = agent.host_root("www.example.com", "site") / "__external_assets" / "cdn.example.com" / "app.css"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("body{}", encoding="utf-8")
        preview_source = agent.host_root("www.example.com", "local_preview") / "__external_assets" / "cdn.example.com" / "app.css"
        preview_source.parent.mkdir(parents=True, exist_ok=True)
        preview_source.write_text("body{}", encoding="utf-8")
        item = CrawlItem(
            url="https://docs.example.com/",
            host="docs.example.com",
            depth=0,
            status="replicated",
            local_preview_path="hosts/docs.example.com/local_preview/index.html",
            deploy_path="hosts/docs.example.com/site/index.html",
        )
        agent.crawl_table[item.url] = item
        for relative in (item.local_preview_path, item.deploy_path):
            page = agent.original_dir / relative
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text('<html><head><link rel="stylesheet" href="/__external_assets/cdn.example.com/app.css"></head></html>', encoding="utf-8")

        agent.repair_missing_local_static_refs()

        self.assertTrue((agent.host_root("docs.example.com", "site") / "__external_assets" / "cdn.example.com" / "app.css").exists())
        self.assertTrue(
            (agent.host_root("docs.example.com", "local_preview") / "__external_assets" / "cdn.example.com" / "app.css").exists()
        )

    def test_verify_static_resource_localization_flags_html_missing_ref(self) -> None:
        agent = make_agent()
        agent.ensure_host("www.example.com")
        item = CrawlItem(
            url="https://www.example.com/",
            host="www.example.com",
            depth=0,
            status="replicated",
            deploy_path="hosts/www.example.com/site/index.html",
        )
        agent.crawl_table[item.url] = item
        page = agent.original_dir / item.deploy_path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text('<html><head><link rel="stylesheet" href="/missing.css"></head></html>', encoding="utf-8")

        issues = agent.find_missing_local_static_refs()

        self.assertEqual(issues[0]["ref"], "/missing.css")
        self.assertEqual(issues[0]["reason"], "html_local_static_ref_missing")


if __name__ == "__main__":
    unittest.main()
