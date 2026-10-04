"""spgr-check-seo-baseline/scripts/seo_baseline.py: the deterministic SEO
check over built HTML. Exercised with inline fixtures, no network and no
browser. A passing page passes, each blocking rule fails on its own, advisory
rules stay advisory until --strict, and a target with no HTML exits 2."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

sb = load_script(REPO / ".claude" / "skills" / "spgr-check-seo-baseline" / "scripts" / "seo_baseline.py")

TITLE = "Expense reporting for small finance teams, by Ledgerly"  # 54 characters
DESCRIPTION = ("Ledgerly turns receipts into approved expense reports in one pass, with policy checks, "
               "card matching, and an audit trail your accountant can read in full.")  # 154 characters

GOOD_PAGE = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE}</title>
<meta name="description" content="{DESCRIPTION}">
<link rel="canonical" href="https://ledgerly.example/">
<meta property="og:title" content="Ledgerly expense reporting">
<meta property="og:description" content="Receipts to approved reports in one pass.">
<meta property="og:image" content="https://ledgerly.example/og.png">
<meta property="og:url" content="https://ledgerly.example/">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Ledgerly"}}</script>
</head>
<body>
<h1>Expense reporting for small finance teams</h1>
<h2>How it works</h2>
<h3>Capture</h3>
<img src="/hero.webp" alt="A reviewed expense report" width="1200" height="630">
</body>
</html>
"""


def write_site(root, pages, sitemap=True, robots=True):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, html in pages.items():
        (root / name).write_text(html)
    if sitemap:
        (root / "sitemap.xml").write_text(
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://ledgerly.example/</loc></url></urlset>')
    if robots:
        (root / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://ledgerly.example/sitemap.xml\n")


class SeoBaselineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def run_script(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sb.main(["seo_baseline.py", *args])
        return rc, buf.getvalue()

    def report(self, *args):
        rc, out = self.run_script(*args, "--json")
        return rc, json.loads(out)

    def failures(self, report, severity=None):
        found = []
        for page in report["pages"]:
            found += [c["check"] for c in page["checks"] if c["status"] == "fail"
                      and (severity is None or c["severity"] == severity)]
        found += [c["check"] for c in report["root"] if c["status"] == "fail"
                  and (severity is None or c["severity"] == severity)]
        return found

    def test_good_page_passes_with_no_failures(self):
        write_site(self.root / "dist", {"index.html": GOOD_PAGE})
        rc, report = self.report("dist")
        self.assertEqual(rc, 0)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(self.failures(report), [])

    def test_default_output_directory_is_autodetected(self):
        write_site(self.root / "dist", {"index.html": GOOD_PAGE})
        rc, report = self.report()
        self.assertEqual(rc, 0)
        self.assertEqual(len(report["pages"]), 1)

    def test_each_blocking_rule_fails_alone(self):
        cases = {
            "title-present": GOOD_PAGE.replace(f"<title>{TITLE}</title>", ""),
            "description-present": GOOD_PAGE.replace(f'<meta name="description" content="{DESCRIPTION}">', ""),
            "h1-single": GOOD_PAGE.replace("<h2>How it works</h2>", "<h1>Second heading</h1>"),
            "noindex-absent": GOOD_PAGE.replace("</head>", '<meta name="robots" content="noindex, nofollow"></head>'),
            "canonical-present": GOOD_PAGE.replace('<link rel="canonical" href="https://ledgerly.example/">',
                                                   '<link rel="canonical" href="/">'),
            "lang-present": GOOD_PAGE.replace('<html lang="en">', "<html>"),
            "viewport-present": GOOD_PAGE.replace('<meta name="viewport" content="width=device-width, initial-scale=1">', ""),
            "jsonld-valid": GOOD_PAGE.replace('{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Ledgerly"}',
                                              '{"@type": "SoftwareApplication", "name": "Ledgerly"'),
            "img-alt": GOOD_PAGE.replace(' alt="A reviewed expense report"', ""),
        }
        for check_id, html in cases.items():
            with self.subTest(check=check_id):
                site = self.root / check_id
                write_site(site, {"index.html": html})
                rc, report = self.report(str(site))
                self.assertEqual(rc, 1)
                self.assertEqual(report["verdict"], "GATE")
                self.assertIn(check_id, self.failures(report, "blocking"))

    def test_duplicate_title_is_blocking(self):
        html = GOOD_PAGE.replace("</head>", "<title>Another title</title></head>")
        write_site(self.root / "dist", {"index.html": html})
        rc, report = self.report("dist")
        self.assertEqual(rc, 1)
        self.assertIn("title-present", self.failures(report, "blocking"))

    def test_advisory_failures_do_not_gate_until_strict(self):
        html = (GOOD_PAGE
                .replace(f"<title>{TITLE}</title>", "<title>Ledgerly</title>")
                .replace('<meta name="twitter:card" content="summary_large_image">', "")
                .replace(' width="1200" height="630"', "")
                .replace("<h3>Capture</h3>", "<h4>Capture</h4>")
                .replace('"@type":"SoftwareApplication"', '"@type":"FAQPage"'))
        write_site(self.root / "dist", {"index.html": html}, sitemap=False, robots=False)
        rc, report = self.report("dist")
        self.assertEqual(rc, 0)
        self.assertEqual(report["verdict"], "PASS")
        advisory = self.failures(report, "advisory")
        for expected in ("title-length", "twitter-card", "img-dimensions", "heading-order",
                         "jsonld-active-types", "sitemap-present", "robots-present"):
            self.assertIn(expected, advisory)
        self.assertEqual(self.failures(report, "blocking"), [])

        rc, strict = self.report("dist", "--strict")
        self.assertEqual(rc, 1)
        self.assertEqual(strict["verdict"], "GATE")
        self.assertTrue(strict["strict"])
        self.assertIn("title-length", self.failures(strict, "blocking"))

    def test_description_that_echoes_the_title_or_ends_in_a_stock_cta_is_advisory(self):
        echo = GOOD_PAGE.replace(f'content="{DESCRIPTION}"', f'content="{TITLE}"')
        cta = GOOD_PAGE.replace(f'content="{DESCRIPTION}"', 'content="Ledgerly does your expenses. Get started."')
        for name, html in (("echo", echo), ("cta", cta)):
            with self.subTest(case=name):
                site = self.root / name
                write_site(site, {"index.html": html})
                _, report = self.report(str(site))
                self.assertIn("description-distinct", self.failures(report, "advisory"))

    def test_malformed_sitemap_is_reported(self):
        write_site(self.root / "dist", {"index.html": GOOD_PAGE}, sitemap=False)
        (self.root / "dist" / "sitemap.xml").write_text("<urlset><url><loc>https://x</loc></url>")
        _, report = self.report("dist")
        self.assertIn("sitemap-present", self.failures(report, "advisory"))

    def test_jsonld_graph_and_separate_root_are_handled(self):
        html = GOOD_PAGE.replace(
            '{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Ledgerly"}',
            '{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"Ledgerly"},'
            '{"@type":"WebSite","url":"https://ledgerly.example/"}]}')
        write_site(self.root / "dist" / "pages", {"index.html": html}, sitemap=False, robots=False)
        write_site(self.root / "dist", {}, sitemap=True, robots=True)
        rc, report = self.report(str(self.root / "dist" / "pages"), "--root", str(self.root / "dist"))
        self.assertEqual(rc, 0)
        self.assertEqual(self.failures(report), [])

    def test_table_output_names_failures_and_verdict(self):
        html = GOOD_PAGE.replace(' alt="A reviewed expense report"', "")
        write_site(self.root / "dist", {"index.html": html})
        rc, out = self.run_script("dist")
        self.assertEqual(rc, 1)
        self.assertIn("img-alt", out)
        self.assertIn("verdict GATE", out)

    def test_no_html_exits_two(self):
        (self.root / "empty").mkdir()
        rc, out = self.run_script("empty")
        self.assertEqual(rc, 2)
        self.assertIn("no HTML file found", out)
        rc, report = self.report("empty")
        self.assertEqual(rc, 2)
        self.assertEqual(report["verdict"], "ERROR")


if __name__ == "__main__":
    unittest.main()
