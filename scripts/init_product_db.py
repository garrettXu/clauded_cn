#!/usr/bin/env python3
"""Initialize the local product database and store product documents."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "site_mirror_agent.db"
DOCS = [
    ("授权网站复刻与汉化双 Agent 总览文档", ROOT / "docs" / "site_mirror_agent_product.md"),
    ("复刻 Agent 产品文档", ROOT / "docs" / "replication_agent_prd.md"),
    ("复刻 Agent 部署声明与 Nginx 配置模板", ROOT / "docs" / "replication_deployment_nginx_template.md"),
    ("复刻 Agent 使用说明", ROOT / "docs" / "replication_agent_usage.md"),
    ("汉化 Agent 产品文档", ROOT / "docs" / "localization_agent_prd.md"),
    ("双 Agent 产品方案三轮审查", ROOT / "docs" / "product_review_rounds.md"),
]


SCHEMA = """
CREATE TABLE IF NOT EXISTS product_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_url TEXT NOT NULL,
    same_domain TEXT NOT NULL,
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    status_code INTEGER,
    content_hash TEXT,
    title TEXT,
    internal_links INTEGER NOT NULL DEFAULT 0,
    external_links INTEGER NOT NULL DEFAULT 0,
    assets INTEGER NOT NULL DEFAULT 0,
    text_samples INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(run_id) REFERENCES validation_runs(id)
);

CREATE TABLE IF NOT EXISTS validation_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    page_url TEXT NOT NULL,
    asset_url TEXT NOT NULL,
    local_path TEXT,
    content_type TEXT,
    size_bytes INTEGER,
    status TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES validation_runs(id)
);
"""


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        for title, doc_path in DOCS:
            content = doc_path.read_text(encoding="utf-8")
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            conn.execute(
                """
                INSERT OR IGNORE INTO product_docs
                    (title, path, content_hash, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, str(doc_path), content_hash, content, now),
            )
            print(f"document={doc_path}")
            print(f"document_hash={content_hash}")

    print(f"database={DB_PATH}")


if __name__ == "__main__":
    main()
