#!/usr/bin/env bash
# Render a generated class, object, or package diagram source to SVG and verify
# the render is clean. Supports both notations:
#   *.puml  rendered with the PlantUML jar (needs Graphviz dot for class layout)
#   *.mmd   rendered with the Mermaid CLI
#
# A render is a VALIDATION FAILURE when it:
#   - exits non-zero, or
#   - emits a PlantUML error annotation into the SVG, or
#   - drops a declared relationship (the rendered SVG has fewer edges than the
#     source declares).
#
# Usage: render-and-verify.sh <src.puml|src.mmd> [out.svg]
# Exit 0 = clean render verified. Exit 1 = validation failure. Exit 2 = usage.
set -euo pipefail

PLANTUML_JAR="${PLANTUML_JAR:-$HOME/.plantuml/plantuml.jar}"

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: render-and-verify.sh <src.puml|src.mmd> [out.svg]" >&2
  exit 2
fi

src="$1"
if [ ! -f "$src" ]; then
  echo "error: source not found: $src" >&2
  exit 2
fi

ext="${src##*.}"
out="${2:-${src%.*}.svg}"

# Count occurrences of a pattern. grep -c counts matching LINES, and a rendered
# SVG is effectively one line, so occurrences are counted with grep -o | wc -l.
count_occurrences() {
  grep -oE "$1" "$2" 2>/dev/null | wc -l | tr -d ' '
}

# Count declared relationships in the source. This is the floor the rendered
# SVG must meet. A dropped relationship leaves a clean image with missing
# semantics, which is the most dangerous failure mode. Comment lines are
# stripped first so a glyph inside a comment does not inflate the count.
count_declared() {
  local stripped
  stripped="$(mktemp)"
  case "$ext" in
    puml) grep -vE "^\s*'" "$src" > "$stripped" || true ;;
    mmd)  grep -vE '^\s*%%' "$src" > "$stripped" || true ;;
  esac
  case "$ext" in
    puml) count_occurrences '(<\|--|<\|\.\.|\*--|o--|-->|\.\.>)' "$stripped" ;;
    mmd)  count_occurrences '(<\|--|\.\.\|>|<\|\.\.|\*--|o--|-->|\.\.>)' "$stripped" ;;
  esac
  rm -f "$stripped"
}

# Count rendered edges in the SVG. PlantUML (Graphviz) tags each edge group
# class="link". Mermaid tags each relationship/flowchart path with a class
# containing relation, edgePath, or flowchart-link.
count_rendered() {
  case "$ext" in
    puml) count_occurrences 'class="link"' "$out" ;;
    mmd)  count_occurrences 'class="[^"]*(relation|edgePath|flowchart-link)[^"]*"' "$out" ;;
  esac
}

declared="$(count_declared)"

case "$ext" in
  puml)
    if [ ! -f "$PLANTUML_JAR" ]; then
      echo "error: PlantUML jar not found at $PLANTUML_JAR (set PLANTUML_JAR)" >&2
      exit 2
    fi
    # -pipe reads the source on stdin and writes the one diagram to stdout, so
    # the output path is fully controlled and does not depend on the @startuml
    # name. -failfast2 makes PlantUML exit non-zero on a syntax error instead
    # of baking a clean error image. SVG goes to $out, stderr is captured.
    errfile="$(mktemp)"
    if ! java -jar "$PLANTUML_JAR" -tsvg -failfast2 -pipe < "$src" > "$out" 2>"$errfile"; then
      echo "FAIL: PlantUML render exited non-zero for $src" >&2
      cat "$errfile" >&2
      rm -f "$errfile"
      exit 1
    fi
    rm -f "$errfile"
    ;;
  mmd)
    if ! err="$(npx @mermaid-js/mermaid-cli@11 -i "$src" -o "$out" 2>&1)"; then
      echo "FAIL: Mermaid render exited non-zero for $src" >&2
      printf '%s\n' "$err" >&2
      exit 1
    fi
    ;;
  *)
    echo "error: unsupported extension .$ext (use .puml or .mmd)" >&2
    exit 2 ;;
esac

if [ ! -f "$out" ]; then
  echo "FAIL: no SVG produced at $out" >&2
  exit 1
fi

# Detect a PlantUML error annotation baked into the SVG. PlantUML writes a
# "Syntax Error" caption into the image even on some non-fatal parse problems.
if grep -qiE 'syntax error|cannot find|an error has occurred' "$out"; then
  echo "FAIL: error annotation found in rendered SVG $out" >&2
  exit 1
fi

rendered="$(count_rendered)"
if [ "$declared" -gt 0 ] && [ "$rendered" -lt "$declared" ]; then
  echo "FAIL: dropped relationship in $out (declared $declared, rendered $rendered)" >&2
  echo "a silently dropped relationship leaves a clean image with missing semantics" >&2
  exit 1
fi

echo "OK: $src -> $out (relationships declared $declared, rendered $rendered)"
