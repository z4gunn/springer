#!/usr/bin/env bash
# Render-and-validate a sequence-diagram source to SVG and fail on any defect:
#   - non-zero renderer exit (a parse error, an unmatched fragment end)
#   - an error annotation drawn into the output image (PlantUML "Syntax Error")
#   - a missing or empty output file
# Runs the structural lint first, so an unbalanced fragment or an unclosed activation
# bar is reported before the renderer is invoked. The renderer is the parse gate; the
# lint is the structural gate that catches the silent Mermaid bar-never-closes case.
#
# Mermaid (.mmd):  npx @mermaid-js/mermaid-cli@11 -i SRC -o SRC.svg
# PlantUML (.puml): java -jar ~/.plantuml/plantuml.jar -failfast2 -tsvg SRC  (writes SRC.svg)
#
# Usage: render-sequence.sh <file.mmd | file.puml> [more files ...]
# Exit 0 = every file rendered and validated. Exit 1 = at least one failure. Exit 2 = usage.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: render-sequence.sh <file.mmd | file.puml> [more files ...]" >&2
  exit 2
fi

here="$(cd "$(dirname "$0")" && pwd)"
plantuml_jar="${PLANTUML_JAR:-$HOME/.plantuml/plantuml.jar}"
status=0

# Structural gate. If the lint fails, do not bother the renderer.
if ! "$here/lint-sequence.sh" "$@"; then
  echo "render-sequence: lint failed, fix structural imbalance before rendering" >&2
  exit 1
fi

for f in "$@"; do
  case "$f" in
    *.mmd)
      out="${f%.mmd}.svg"
      if ! err=$(npx @mermaid-js/mermaid-cli@11 -i "$f" -o "$out" 2>&1); then
        echo "FAIL $f: mermaid render exited non-zero" >&2
        echo "$err" | tail -5 >&2
        status=1
        continue
      fi
      ;;
    *.puml)
      out="${f%.puml}.svg"
      if [ ! -f "$plantuml_jar" ]; then
        echo "FAIL $f: plantuml.jar not found at $plantuml_jar (set PLANTUML_JAR)" >&2
        status=1
        continue
      fi
      if ! err=$(java -jar "$plantuml_jar" -failfast2 -tsvg "$f" 2>&1); then
        echo "FAIL $f: plantuml render exited non-zero" >&2
        echo "$err" | tail -5 >&2
        status=1
        continue
      fi
      # PlantUML can exit 0 yet draw an error annotation into the SVG. Treat that as a fail.
      if [ -f "$out" ] && grep -q "Syntax Error" "$out"; then
        echo "FAIL $f: plantuml drew a Syntax Error annotation into $out" >&2
        status=1
        continue
      fi
      ;;
    *)
      echo "FAIL $f: unknown extension, expected .mmd or .puml" >&2
      status=1
      continue
      ;;
  esac

  if [ ! -s "$out" ]; then
    echo "FAIL $f: no output produced at $out" >&2
    status=1
    continue
  fi
  echo "OK   $f -> $out"
done

exit "$status"
