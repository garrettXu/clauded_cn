from __future__ import annotations

import unittest

from scripts.serve_replica import host_prefix, rewrite_localhost_content


class ServeReplicaTests(unittest.TestCase):
    def test_rewrite_localhost_content_to_single_port_paths(self) -> None:
        html = b'''
        <a href="http://localhost:8301/docs/">Docs</a>
        <img src="/images/logo.png" srcset="/images/logo.png 1x, /images/logo@2x.png 2x">
        <link href="/assets/app.css" rel="stylesheet">
        '''

        rewritten = rewrite_localhost_content(
            html,
            "text/html",
            "www.example.com",
            {8300: "www.example.com", 8301: "docs.example.com"},
        ).decode("utf-8")

        self.assertIn(f'href="{host_prefix("docs.example.com")}/docs/"', rewritten)
        self.assertIn(f'src="{host_prefix("www.example.com")}/images/logo.png"', rewritten)
        self.assertIn(f'{host_prefix("www.example.com")}/images/logo@2x.png 2x', rewritten)
        self.assertIn(f'href="{host_prefix("www.example.com")}/assets/app.css"', rewritten)

    def test_rewrite_css_root_urls(self) -> None:
        css = b"body{background:url('/hero.jpg')}@font-face{src:url(/font.woff2)}"

        rewritten = rewrite_localhost_content(css, "text/css", "www.example.com", {}).decode("utf-8")

        self.assertIn(f"url('{host_prefix('www.example.com')}/hero.jpg')", rewritten)
        self.assertIn(f"url({host_prefix('www.example.com')}/font.woff2)", rewritten)


if __name__ == "__main__":
    unittest.main()
