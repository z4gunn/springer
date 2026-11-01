#!/usr/bin/env bash
# Render a state-diagram source file to SVG and fail on any render error.
# Picks the renderer from the file extension: .mmd uses mermaid-cli, .puml uses
# plantuml.jar. A render is a validation failure when the renderer exits
# non-zero, emits an error annotation into the SVG, or produces no SVG. The
# caller views the SVG before delivery; this script gates the obvious failures.
#
# Usage: render-validate.sh <src.mmd|src.puml> [out.svg]
# Exit 0 = clean render. Exit 1 = render failure. Exit 2 = usage error.
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: render-validate.sh <src.mmd|src.puml> [out.svg]" >&2
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
    if ! err=$(npx @mermaid-js/mermaid-cli@11 -i "$src" -o "$out" 2>&1); then
      echo "render failed (mermaid, non-zero exit): $src" >&2
      echo "$err" >&2
      exit 1
    fi
    ;;
  puml)
    # plantuml.jar writes <src-basename>.svg next to the source; it ignores an
    # output filename, so render there and move into place if a name was given.
    jar="${PLANTUML_JAR:-$HOME/.plantuml/plantuml.jar}"
    if [ ! -f "$jar" ]; then
      echo "error: plantuml.jar not found at $jar (set PLANTUML_JAR)" >&2
      exit 2
    fi
    default_out="${src%.*}.svg"
    if ! err=$(java -jar "$jar" -tsvg "$src" 2>&1); then
      echo "render failed (plantuml, non-zero exit): $src" >&2
      echo "$err" >&2
      exit 1
    fi
    if [ ! -f "$default_out" ]; then
      echo "render failed (plantuml produced no svg): $src" >&2
      echo "$err" >&2
      exit 1
    fi
    out="${2:-$default_out}"
    if [ "$out" != "$default_out" ]; then
      mv "$default_out" "$out"
    fi
    ;;
  *)
    echo "error: unknown extension .$ext (expected .mmd or .puml)" >&2
    exit 2
    ;;
esac

# Both renderers can exit 0 yet stamp an error message into the SVG. Treat any
# rendered error annotation as a failure, because a clean exit with broken
# semantics is the most dangerous outcome.
if grep -qiE 'syntax error|parse error|cannot|^error\b' "$out" 2>/dev/null; then
  echo "render produced an error annotation in the svg: $out" >&2
  grep -iE 'syntax error|parse error|cannot|^error\b' "$out" | head -3 >&2
  exit 1
fi

echo "rendered: $out"
