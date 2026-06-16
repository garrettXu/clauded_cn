from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.replication_agent import (
    CrawlItem,
    DomainPolicy,
    ReplicationAgent,
    ReplicationConfig,
    ResourceItem,
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


if __name__ == "__main__":
    unittest.main()
