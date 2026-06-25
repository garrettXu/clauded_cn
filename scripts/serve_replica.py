#!/usr/bin/env python3
"""Serve a replicated static mirror using one local port per source host."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def serve_host(port: int, directory: Path) -> None:
    handler = functools.partial(QuietHandler, directory=str(directory))
    with ReusableTCPServer(("127.0.0.1", port), handler) as server:
        server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve replicated hosts on their assigned local ports.")
    parser.add_argument(
        "replica_dir",
        nargs="?",
        default="output/replication_test/original",
        help="Path to mirror/original, or a single static site directory.",
    )
    parser.add_argument("--port", type=int, help="Port for serving a single static site directory.")
    parser.add_argument("--bind", default="127.0.0.1", help="Bind address for single-directory serving.")
    args = parser.parse_args()

    replica_dir = Path(args.replica_dir).resolve()
    manifest_path = replica_dir / "manifest.json"
    if not manifest_path.exists():
        port = args.port or 8700
        handler = functools.partial(QuietHandler, directory=str(replica_dir))
        with ReusableTCPServer((args.bind, port), handler) as server:
            print(f"{replica_dir} -> http://{args.bind}:{port}")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                return 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    hosts = manifest.get("hosts", [])
    if args.port and len(hosts) > 1:
        raise SystemExit("--port can only override a manifest with one host; multi-host mirrors use manifest ports.")

    threads: list[threading.Thread] = []
    for host in hosts:
        port = int(args.port or host["local_port"])
        directory = replica_dir / host["local_preview_root"]
        if not directory.exists():
            continue
        thread = threading.Thread(target=serve_host, args=(port, directory), daemon=True)
        thread.start()
        threads.append(thread)
        print(f"{host['source_host']} -> http://localhost:{port} ({directory})")

    if not threads:
        raise SystemExit("No hosts to serve.")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
