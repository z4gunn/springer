#!/usr/bin/env bash
# Render and validate a design-pattern diagram pair: the structure class diagram
# and the collaboration sequence diagram. Both views are always required.
#
# A render is a validation FAILURE if the renderer exits non-zero, if it writes
# an error annotation into the output image, or if a declared element is dropped
# from the rendered SVG. A clean render with missing semantics is the most
# dangerous outcome, so this script greps the SVG for every declared role and
# fails when one did not make it into the image.
#
# Usage:
#   render-pattern.sh <structure-src> <collaboration-src> [out-dir]
# where each src is a .puml or .mmd file. The structure source is also scanned
# for its declared stereotype roles, each of which must appear in the SVG.
#
# Example:
#   render-pattern.sh order.structure.puml order.collab.puml ./diagrams
set -euo pipefail

PLANTUML_JAR="${PLANTUML_JAR:-$HOME/.plantuml/plantuml.jar}"

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "usage: render-pattern.sh <structure-src> <collaboration-src> [out-dir]" >&2
  exit 2
fi

structure_src="$1"
collab_src="$2"
out_dir="${3:-$(dirname "$structure_src")}"

for f in "$structure_src" "$collab_src"; do
  if [ ! -f "$f" ]; then
    echo "error: source not found: $f" >&2
    exit 2
  fi
done

mkdir -p "$out_dir"
fail=0

# Render one source to SVG. Detects a non-zero renderer exit and an error
# annotation written into the SVG. Echoes the produced SVG path on success.
render_one() {
  src="$1"
  base="$(basename "${src%.*}")"
  out="$out_dir/$base.svg"
  case "$src" in
    *.puml)
      abs_out="$(cd "$out_dir" && pwd)"
      if ! err="$(java -jar "$PLANTUML_JAR" -tsvg -o "$abs_out" "$src" 2>&1)"; then
        echo "FAIL render (plantuml exit nonzero): $src" >&2
        echo "$err" >&2
        return 1
      fi
      # PlantUML names the SVG after the @startuml <name> directive when present,
      # otherwise after the source basename. Resolve the actual name.
      diagram_name="$(sed -n 's/^[[:space:]]*@startuml[[:space:]]\{1,\}\([^[:space:]]\{1,\}\).*/\1/p' "$src" | head -1)"
      if [ -n "$diagram_name" ] && [ -f "$abs_out/$diagram_name.svg" ]; then
        out="$abs_out/$diagram_name.svg"
      fi
      if [ ! -f "$out" ]; then
        echo "FAIL render (no svg produced): $src" >&2
        echo "$err" >&2
        return 1
      fi
      ;;
    *.mmd)
      if ! err="$(npx @mermaid-js/mermaid-cli@11 -i "$src" -o "$out" 2>&1)"; then
        echo "FAIL render (mermaid exit nonzero): $src" >&2
        echo "$err" >&2
        return 1
      fi
      ;;
    *)
      echo "FAIL: unknown source type (need .puml or .mmd): $src" >&2
      return 1
      ;;
  esac
  # An error annotation in the image is a silent failure on a zero exit.
  if grep -qiE "syntax error|cannot find|some diagram description contains errors|parse error" "$out"; then
    echo "FAIL render (error annotation in svg): $out" >&2
    return 1
  fi
  echo "$out"
}

echo "rendering structure view: $structure_src"
if ! structure_svg="$(render_one "$structure_src")"; then
  fail=1
else
  echo "  ok -> $structure_svg"
fi

echo "rendering collaboration view: $collab_src"
if ! collab_svg="$(render_one "$collab_src")"; then
  fail=1
else
  echo "  ok -> $collab_svg"
fi

# Dropped-element check on the structure view. Every stereotype role declared in
# the source must appear in the rendered SVG. A silently dropped role leaves a
# clean image with missing semantics. Two source forms carry a role: the literal
# spot stereotype <<RoleName>> used on the concrete view, and the preamble category
# macro CREATIONAL_ROLE(RoleName), STRUCTURAL_ROLE(RoleName), or BEHAVIORAL_ROLE(
# RoleName) used on the abstract view. Extract the role name from both.
if [ "$fail" -eq 0 ]; then
  literal_roles="$(grep -oE '<<[[:space:]]*(\([A-Za-z],#?[0-9A-Fa-f]+\)[[:space:]]*)?[A-Za-z][A-Za-z0-9_]*[[:space:]]*>>' "$structure_src" 2>/dev/null \
    | sed -E 's/<<[[:space:]]*(\([A-Za-z],#?[0-9A-Fa-f]+\)[[:space:]]*)?//; s/[[:space:]]*>>//' || true)"
  macro_roles="$(grep -oE '(CREATIONAL|STRUCTURAL|BEHAVIORAL)_ROLE\([A-Za-z][A-Za-z0-9_]*\)' "$structure_src" 2>/dev/null \
    | sed -E 's/.*_ROLE\(//; s/\)//' || true)"
  roles="$(printf '%s\n%s\n' "$literal_roles" "$macro_roles" | grep -v '^$' | sort -u)"
  if [ -z "$roles" ]; then
    echo "FAIL: structure source declares no role stereotype; a pattern structure must bind roles" >&2
    fail=1
  else
    for role in $roles; do
      if ! grep -q "$role" "$structure_svg"; then
        echo "FAIL dropped element: role <<$role>> declared in source but absent from $structure_svg" >&2
        fail=1
      fi
    done
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo "RENDER VALIDATION FAILED" >&2
  exit 1
fi
echo "RENDER VALIDATION PASSED (both views rendered, all roles present)"
