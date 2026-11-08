#!/usr/bin/env python3
"""Check built HTML pages against the structural half of the SEO standards.

Deterministic, no model, no browser, no network. Parses every HTML file under
a built output directory with the stdlib html.parser and answers the rules in
.claude/references/seo-standards.md that static markup can answer: title and
description presence and length, one H1 and heading order, canonical, lang
and viewport, noindex, Open Graph and Twitter card completeness, JSON-LD
validity and retired types, image alt and dimensions. At the site root it
checks that sitemap.xml exists and is well formed and that robots.txt exists.
It does not measure Core Web Vitals, fetch sitemap URLs, or validate schema
against schema.org. The calling skill names those follow-ups.

Each check is blocking or advisory. The verdict is PASS when no blocking check
fails and GATE otherwise. --strict promotes every advisory check to blocking,
which is how the brochure profile runs it.

Usage:
    seo_baseline.py [<target> ...] [--root <dir>] [--strict] [--json]

<target> is a built output directory or an .html file. With no target the
script looks for dist/, out/, build/, public/, or _site/ under the current
directory, in that order. --root names the directory that holds sitemap.xml
and robots.txt when it is not the first target directory.

Exit codes: 0 PASS, 1 GATE, 2 could not run (no HTML file found).
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_OUTPUT_DIRS = ("dist", "out", "build", "public", "_site")
SKIP_DIRS = {"node_modules", ".git", ".next", ".cache"}
TITLE_RANGE = (50, 60)
DESCRIPTION_RANGE = (150, 160)
STOCK_CTAS = ("get started", "learn more", "try it free", "sign up today", "start now", "click here")
RETIRED_TYPES = {"FAQPage", "HowTo"}
OG_REQUIRED = ("og:title", "og:description", "og:image", "og:url")
ABSOLUTE_URL = re.compile(r"^https?://", re.I)


class PageParser(HTMLParser):
    """Collect the head and heading facts the checks read."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titles = []
        self.metas = []
        self.canonicals = []
        self.lang = None
        self.headings = []
        self.images = []
        self.jsonld = []
        self._in_title = False
        self._title_buf = []
        self._heading_level = None
        self._heading_buf = []
        self._in_jsonld = False
        self._jsonld_buf = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
            self._title_buf = []
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link" and a.get("rel", "").lower().split() == ["canonical"]:
            self.canonicals.append(a.get("href", ""))
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading_level = int(tag[1])
            self._heading_buf = []
        elif tag == "img":
            self.images.append(a)
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_buf = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self.titles.append("".join(self._title_buf).strip())
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._heading_level:
            self.headings.append((self._heading_level, "".join(self._heading_buf).strip()))
            self._heading_level = None
        elif tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld.append("".join(self._jsonld_buf))

    def handle_data(self, data):
        if self._in_title:
            self._title_buf.append(data)
        if self._heading_level:
            self._heading_buf.append(data)
        if self._in_jsonld:
            self._jsonld_buf.append(data)


def meta_value(metas, key):
    """The content of the first meta whose name or property matches key."""
    for m in metas:
        if m.get("name", "").lower() == key or m.get("property", "").lower() == key:
            return m.get("content", "")
    return None


def normalize(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def jsonld_types(block):
    """Every @type found in a parsed JSON-LD block, including @graph items."""
    types = []
    nodes = block if isinstance(block, list) else [block]
    for node in nodes:
        if not isinstance(node, dict):
            continue
        t = node.get("@type")
        if isinstance(t, list):
            types.extend(str(x) for x in t)
        elif t:
            types.append(str(t))
        for item in node.get("@graph", []) if isinstance(node.get("@graph"), list) else []:
            types.extend(jsonld_types(item))
    return types


def check(checks, check_id, severity, ok, detail):
    checks.append({"check": check_id, "severity": severity, "status": "pass" if ok else "fail", "detail": detail})


def check_page(html):
    """Run every page-level check and return the list of check results."""
    p = PageParser()
    p.feed(html)
    p.close()
    checks = []

    titles = [t for t in p.titles if t]
    check(checks, "title-present", "blocking", len(titles) == 1,
          "one non-empty title" if len(titles) == 1 else f"{len(titles)} title elements")
    description = meta_value(p.metas, "description")
    check(checks, "description-present", "blocking", bool(description and description.strip()),
          "meta description present" if description else "meta description missing")
    h1s = [h for h in p.headings if h[0] == 1]
    check(checks, "h1-single", "blocking", len(h1s) == 1, f"{len(h1s)} h1 elements")
    robots = normalize(meta_value(p.metas, "robots"))
    check(checks, "noindex-absent", "blocking", "noindex" not in robots,
          "no noindex" if "noindex" not in robots else f"robots meta is '{robots}'")
    canonical_ok = len(p.canonicals) == 1 and bool(ABSOLUTE_URL.match(p.canonicals[0]))
    check(checks, "canonical-present", "blocking", canonical_ok,
          p.canonicals[0] if canonical_ok else f"{len(p.canonicals)} canonical links, absolute http(s) required")
    check(checks, "lang-present", "blocking", bool(p.lang), f"lang='{p.lang}'" if p.lang else "html lang missing")
    viewport = meta_value(p.metas, "viewport")
    check(checks, "viewport-present", "blocking", bool(viewport), "viewport meta present" if viewport else "viewport meta missing")

    jsonld_ok, jsonld_detail, found_types = True, f"{len(p.jsonld)} JSON-LD blocks", []
    for raw in p.jsonld:
        try:
            block = json.loads(raw)
        except json.JSONDecodeError as exc:
            jsonld_ok, jsonld_detail = False, f"JSON-LD does not parse: {exc.msg}"
            break
        nodes = block if isinstance(block, list) else [block]
        for node in nodes:
            if not isinstance(node, dict) or "@context" not in node or ("@type" not in node and "@graph" not in node):
                jsonld_ok, jsonld_detail = False, "a JSON-LD block lacks @context or @type"
        found_types.extend(jsonld_types(block))
    check(checks, "jsonld-valid", "blocking", jsonld_ok, jsonld_detail)

    missing_alt = sum(1 for img in p.images if "alt" not in img)
    check(checks, "img-alt", "blocking", missing_alt == 0,
          f"{len(p.images)} images with alt" if missing_alt == 0 else f"{missing_alt} images without alt")

    title = titles[0] if titles else ""
    check(checks, "title-length", "advisory", TITLE_RANGE[0] <= len(title) <= TITLE_RANGE[1],
          f"title is {len(title)} characters, target {TITLE_RANGE[0]} to {TITLE_RANGE[1]}")
    dlen = len((description or "").strip())
    check(checks, "description-length", "advisory", DESCRIPTION_RANGE[0] <= dlen <= DESCRIPTION_RANGE[1],
          f"description is {dlen} characters, target {DESCRIPTION_RANGE[0]} to {DESCRIPTION_RANGE[1]}")
    ndesc = normalize(description)
    echo = bool(ndesc) and ndesc == normalize(title)
    stock = any(ndesc.rstrip(".!").endswith(c) for c in STOCK_CTAS)
    check(checks, "description-distinct", "advisory", not echo and not stock,
          "description repeats the title" if echo else "description ends in a stock call to action" if stock
          else "description is distinct")
    order_ok, prev = True, 0
    for level, _ in p.headings:
        if prev and level > prev + 1:
            order_ok = False
            break
        prev = level
    check(checks, "heading-order", "advisory", order_ok,
          "headings descend one level at a time" if order_ok else "a heading skips a level")
    missing_og = [k for k in OG_REQUIRED if not meta_value(p.metas, k)]
    check(checks, "og-complete", "advisory", not missing_og,
          "Open Graph complete" if not missing_og else "missing " + ", ".join(missing_og))
    check(checks, "twitter-card", "advisory", bool(meta_value(p.metas, "twitter:card")),
          "twitter:card present" if meta_value(p.metas, "twitter:card") else "twitter:card missing")
    unsized = sum(1 for img in p.images if not (img.get("width") and img.get("height")))
    check(checks, "img-dimensions", "advisory", unsized == 0,
          "every image has width and height" if unsized == 0 else f"{unsized} images without width and height")
    retired = sorted(set(found_types) & RETIRED_TYPES)
    check(checks, "jsonld-active-types", "advisory", not retired,
          "no retired schema types" if not retired else "retired types emitted: " + ", ".join(retired))
    return checks


def check_root(root):
    """Sitemap and robots presence at the site root, advisory."""
    checks = []
    sitemap = Path(root) / "sitemap.xml"
    if not sitemap.exists():
        check(checks, "sitemap-present", "advisory", False, "sitemap.xml missing at the site root")
    else:
        try:
            tree = ET.parse(sitemap)
            urls = [e for e in tree.iter() if e.tag.endswith("}loc") or e.tag == "loc"]
            check(checks, "sitemap-present", "advisory", True, f"sitemap.xml lists {len(urls)} URLs")
            check(checks, "sitemap-size", "advisory", len(urls) <= 50000, f"{len(urls)} URLs, ceiling 50000 per file")
        except ET.ParseError as exc:
            check(checks, "sitemap-present", "advisory", False, f"sitemap.xml does not parse: {exc}")
    robots = Path(root) / "robots.txt"
    check(checks, "robots-present", "advisory", robots.exists(),
          "robots.txt present" if robots.exists() else "robots.txt missing at the site root")
    return checks


def collect_html(targets):
    files = []
    for t in targets:
        t = Path(t)
        if t.is_file() and t.suffix.lower() in (".html", ".htm"):
            files.append(t)
        elif t.is_dir():
            for dirpath, dirnames, filenames in os.walk(t):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for f in sorted(filenames):
                    if f.lower().endswith((".html", ".htm")):
                        files.append(Path(dirpath) / f)
    return sorted(set(files))


def resolve_targets(args_targets):
    if args_targets:
        return [Path(t) for t in args_targets]
    for name in DEFAULT_OUTPUT_DIRS:
        if Path(name).is_dir():
            return [Path(name)]
    return []


def promote(checks, strict):
    if strict:
        for c in checks:
            c["severity"] = "blocking"
    return checks


def print_table(report):
    for page in report["pages"]:
        for c in page["checks"]:
            if c["status"] == "fail":
                print(f"{page['path']}  {c['check']:22} {c['severity']:9} {c['status']:5} {c['detail']}")
    for c in report["root"]:
        if c["status"] == "fail":
            print(f"{report['root_dir']}  {c['check']:22} {c['severity']:9} {c['status']:5} {c['detail']}")
    print(f"pages {len(report['pages'])}  blocking failures {report['blocking_failures']}  "
          f"advisory failures {report['advisory_failures']}  verdict {report['verdict']}")


def main(argv):
    parser = argparse.ArgumentParser(description="SEO baseline check over built HTML")
    parser.add_argument("targets", nargs="*", help="built output directory or .html files")
    parser.add_argument("--root", help="directory holding sitemap.xml and robots.txt")
    parser.add_argument("--strict", action="store_true", help="promote advisory checks to blocking")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv[1:])

    targets = resolve_targets(args.targets)
    files = collect_html(targets)
    if not files:
        msg = {"verdict": "ERROR", "detail": "no HTML file found", "targets": [str(t) for t in targets]}
        print(json.dumps(msg) if args.json else "seo-baseline: no HTML file found under " + (", ".join(str(t) for t in targets) or "the default output directories"))
        return 2

    root = Path(args.root) if args.root else next((t for t in targets if t.is_dir()), files[0].parent)
    pages = []
    for f in files:
        try:
            html = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            html = ""
            sys.stderr.write(f"seo-baseline: cannot read {f}: {exc}\n")
        pages.append({"path": str(f), "checks": promote(check_page(html), args.strict)})
    root_checks = promote(check_root(root), args.strict)

    all_checks = [c for p in pages for c in p["checks"]] + root_checks
    blocking = sum(1 for c in all_checks if c["status"] == "fail" and c["severity"] == "blocking")
    advisory = sum(1 for c in all_checks if c["status"] == "fail" and c["severity"] == "advisory")
    report = {
        "root_dir": str(root),
        "strict": args.strict,
        "pages": pages,
        "root": root_checks,
        "blocking_failures": blocking,
        "advisory_failures": advisory,
        "verdict": "PASS" if blocking == 0 else "GATE",
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_table(report)
    return 0 if blocking == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
