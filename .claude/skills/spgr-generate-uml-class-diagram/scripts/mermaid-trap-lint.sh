#!/usr/bin/env bash
# Lint a Mermaid classDiagram source for the known traps that Mermaid cannot
# express, and ROUTE those cases to PlantUML as a GATE, not a warning. A trap
# that ships as Mermaid renders cleanly with wrong or missing semantics, so a
# detected trap blocks (exit 3) rather than advising.
#
# Traps detected:
#   1. Comma-separated generics, e.g. List~K,V~ or Map~String,Entry~.
#      Mermaid breaks on the comma inside ~...~.
#   2. Nested namespaces. Mermaid namespace support is fragile and does not nest.
#   3. Package annotations, e.g. <<package>>. Mermaid carries no package
#      annotation on a class.
#
# Usage: mermaid-trap-lint.sh <src.mmd>
# Exit 0 = no trap, Mermaid is acceptable.
# Exit 3 = trap found, GATE: regenerate in PlantUML (assets/templates/*.puml).
# Exit 2 = usage error.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: mermaid-trap-lint.sh <src.mmd>" >&2
  exit 2
fi

src="$1"
if [ ! -f "$src" ]; then
  echo "error: source not found: $src" >&2
  exit 2
fi

# Strip %% comment lines before scanning so a documented caveat does not trip.
body="$(grep -vE '^\s*%%' "$src" || true)"

traps=0

# 1. comma-separated generic inside ~...~
if printf '%s\n' "$body" | grep -qE '~[^~]*,[^~]*~'; then
  echo "TRAP: comma-separated generic (e.g. List~K,V~). Mermaid breaks on the comma." >&2
  traps=$((traps + 1))
fi

# 2. nested namespace: a namespace keyword that contains another namespace.
ns_count="$(printf '%s\n' "$body" | grep -cE '^\s*namespace\b' || true)"
if [ "$ns_count" -gt 1 ]; then
  echo "TRAP: nested or multiple namespaces ($ns_count). Mermaid namespace support is fragile and does not nest." >&2
  traps=$((traps + 1))
fi

# 3. package annotation on a class.
if printf '%s\n' "$body" | grep -qiE '<<\s*package\s*>>'; then
  echo "TRAP: package annotation (<<package>>). Mermaid carries no package annotation." >&2
  traps=$((traps + 1))
fi

if [ "$traps" -gt 0 ]; then
  echo "GATE: $traps Mermaid trap(s) found in $src." >&2
  echo "ROUTE to PlantUML. Regenerate this view as .puml using the matching golden template in assets/templates/." >&2
  exit 3
fi

echo "OK: no Mermaid trap in $src. Mermaid is acceptable for this standalone Markdown view."
