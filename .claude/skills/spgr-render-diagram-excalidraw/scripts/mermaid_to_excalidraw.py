"""Convert a Mermaid source file to an editable .excalidraw file, then render a PNG.

Runs the @excalidraw/mermaid-to-excalidraw and @excalidraw/excalidraw libraries
inside a real DOM (Playwright headless Chromium), not jsdom, because the
conversion relies on document.createElement and Mermaid getBBox layout. Both
library versions are pinned in assets/convert_template.html.

Usage (run with the global excalidraw-diagram skill's Playwright venv):
    ~/.claude/skills/excalidraw-diagram/references/.venv/bin/python \
        mermaid_to_excalidraw.py <source.mmd> [--excalidraw out.excalidraw] [--png out.png] \
        [--scale 2] [--width 1920] [--no-render]

Outputs, written next to the source unless overridden:
    <source>.excalidraw   the editable conversion seed
    <source>.png          the rendered PNG (skipped with --no-render)

Exit status is non-zero on any conversion or render failure, with stderr detail.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The conversion and render template lives in this skill's assets directory.
TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "convert_template.html"


def build_excalidraw_file(elements: list[dict], files: dict) -> dict:
    """Wrap converted elements in a valid .excalidraw document."""
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "spgr-render-diagram-excalidraw",
        "elements": elements,
        "appState": {
            "viewBackgroundColor": "#ffffff",
            "gridSize": 20,
        },
        "files": files or {},
    }


def compute_bounding_box(elements: list[dict]) -> tuple[float, float, float, float]:
    """Bounding box (min_x, min_y, max_x, max_y) across live elements."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for el in elements:
        if el.get("isDeleted"):
            continue
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)
        if el.get("type") in ("arrow", "line") and "points" in el:
            for px, py in el["points"]:
                min_x = min(min_x, x + px)
                min_y = min(min_y, y + py)
                max_x = max(max_x, x + px)
                max_y = max(max_y, y + py)
        else:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + abs(w))
            max_y = max(max_y, y + abs(h))
    if min_x == float("inf"):
        return (0, 0, 800, 600)
    return (min_x, min_y, max_x, max_y)


def run(
    source_path: Path,
    excalidraw_path: Path,
    png_path: Path | None,
    scale: int,
    max_width: int,
) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "ERROR: playwright not importable. Run this script with the global "
            "excalidraw-diagram skill venv interpreter: "
            "~/.claude/skills/excalidraw-diagram/references/.venv/bin/python",
            file=sys.stderr,
        )
        sys.exit(1)

    if not TEMPLATE.exists():
        print(f"ERROR: conversion template not found at {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    mermaid_source = source_path.read_text(encoding="utf-8")
    template_url = TEMPLATE.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": max_width, "height": 1080},
            device_scale_factor=scale,
        )

        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(template_url)
        try:
            # The ESM imports are fetched from esm.sh at runtime. A network
            # failure or a moved version surfaces as a load timeout here.
            page.wait_for_function("window.__moduleReady === true", timeout=45000)
        except Exception:
            browser.close()
            detail = "; ".join(page_errors) or "no page error captured"
            print(
                "ERROR: conversion modules did not load. This step needs network "
                "access to esm.sh for the pinned library versions. Detail: " + detail,
                file=sys.stderr,
            )
            sys.exit(1)

        # Step 1: parseMermaidToExcalidraw then convertToExcalidrawElements.
        convert = page.evaluate("(src) => window.convertMermaid(src)", mermaid_source)
        if not convert or not convert.get("success"):
            browser.close()
            msg = convert.get("error") if convert else "convertMermaid returned null"
            print(f"ERROR: Mermaid conversion failed: {msg}", file=sys.stderr)
            sys.exit(1)

        elements = convert.get("elements") or []
        files = convert.get("files") or {}
        if not elements:
            browser.close()
            print(
                "ERROR: conversion produced zero elements. The source may be an "
                "unsupported Mermaid type. See references/source-type-decision-tree.md.",
                file=sys.stderr,
            )
            sys.exit(1)

        doc = build_excalidraw_file(elements, files)
        excalidraw_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        print(f"wrote {excalidraw_path} ({len(elements)} elements)")

        if png_path is None:
            browser.close()
            return

        # Step 2: render the converted document to a PNG in the same DOM.
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        padding = 80
        vp_width = min(int(max_x - min_x + padding * 2), max_width)
        vp_height = max(int(max_y - min_y + padding * 2), 600)
        page.set_viewport_size({"width": max(vp_width, 200), "height": vp_height})

        result = page.evaluate("(d) => window.renderDiagram(d)", doc)
        if not result or not result.get("success"):
            browser.close()
            msg = result.get("error") if result else "renderDiagram returned null"
            print(f"ERROR: PNG render failed: {msg}", file=sys.stderr)
            sys.exit(1)

        page.wait_for_function("window.__renderComplete === true", timeout=15000)
        svg_el = page.query_selector("#root svg")
        if svg_el is None:
            browser.close()
            print("ERROR: no SVG element found after render", file=sys.stderr)
            sys.exit(1)

        svg_el.screenshot(path=str(png_path))
        browser.close()
        print(f"wrote {png_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a Mermaid source to an editable .excalidraw file and PNG."
    )
    parser.add_argument("input", type=Path, help="Path to Mermaid source (.mmd)")
    parser.add_argument("--excalidraw", type=Path, default=None, help="Output .excalidraw path")
    parser.add_argument("--png", type=Path, default=None, help="Output PNG path")
    parser.add_argument("--scale", type=int, default=2, help="Device scale factor (default 2)")
    parser.add_argument("--width", type=int, default=1920, help="Max viewport width (default 1920)")
    parser.add_argument("--no-render", action="store_true", help="Skip PNG render")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    excalidraw_path = args.excalidraw or args.input.with_suffix(".excalidraw")
    png_path = None if args.no_render else (args.png or args.input.with_suffix(".png"))

    run(args.input, excalidraw_path, png_path, args.scale, args.width)


if __name__ == "__main__":
    main()
