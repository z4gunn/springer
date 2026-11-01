#!/usr/bin/env bash
# Render an activity-diagram source to SVG and fail loudly on any error.
# Dispatches on extension: .mmd renders with the Mermaid CLI, .puml with plantuml.jar.
# A render is a validation failure if the tool exits non-zero, if PlantUML writes an
# error annotation into the image, or if a declared node label is dropped from the SVG.
# The caller checks dropped-element coverage; this script checks exit code and error markers.
#
# Usage: render-diagram.sh <src.mmd|src.puml> [out.svg]
# Example: render-diagram.sh diagram.mmd diagram.svg
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: render-diagram.sh <src.mmd|src.puml> [out.svg]" >&2
  exit 2
fi

src="$1"
if [ ! -f "$src" ]; then
  echo "error: source not found: $src" >&2
  exit 2
fi

ext="${src##*.}"
case "$ext" in
  mmd)
    out="${2:-${src%.*}.svg}"
    err="$(mktemp)"
    trap 'rm -f "$err"' EXIT
    if ! npx @mermaid-js/mermaid-cli@11 -i "$src" -o "$out" 2>"$err"; then
      echo "error: mermaid render failed for $src" >&2
      cat "$err" >&2
      exit 1
    fi
    if [ ! -s "$out" ]; then
      echo "error: mermaid produced no output for $src" >&2
      exit 1
    fi
    echo "rendered: $out"
    ;;
  puml)
    # plantuml.jar writes <src>.svg next to the source; the optional out arg is honored by moving it.
    err="$(mktemp)"
    trap 'rm -f "$err"' EXIT
    if ! java -jar "$HOME/.plantuml/plantuml.jar" -tsvg "$src" 2>"$err"; then
      echo "error: plantuml render failed for $src" >&2
      cat "$err" >&2
      exit 1
    fi
    produced="${src%.*}.svg"
    if [ ! -s "$produced" ]; then
      echo "error: plantuml produced no output for $src" >&2
      cat "$err" >&2
      exit 1
    fi
    # PlantUML renders a syntax error as an SVG containing the marker text rather than exiting non-zero.
    if grep -q "syntax error\|Syntax Error\|cannot be parsed\|An error has occured" "$produced"; then
      echo "error: plantuml wrote an error annotation into $produced" >&2
      grep -m1 "error\|Error" "$produced" >&2 || true
      exit 1
    fi
    if [ "${2:-}" != "" ] && [ "$2" != "$produced" ]; then
      mv "$produced" "$2"
      produced="$2"
    fi
    echo "rendered: $produced"
    ;;
  *)
    echo "error: unsupported extension .$ext (expected .mmd or .puml)" >&2
    exit 2
    ;;
esac
