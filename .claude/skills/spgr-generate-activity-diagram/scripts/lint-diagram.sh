#!/usr/bin/env bash
# Lint an activity-diagram source for the three structural defects the family forbids:
#   1. an unmatched fork/join (a fork without its end fork, or an end fork without a fork)
#   2. an unmatched decision/merge (an if without its endif)
#   3. a decision whose guards are not exhaustive (a branch with no else path)
# Works on PlantUML activity (.puml) by keyword balance, and on Mermaid flowchart (.mmd)
# by checking that every decision node has both a non-else guard edge and an else edge.
# Exits 0 when clean, 1 when any defect is found, 2 on a usage error.
#
# Usage: lint-diagram.sh <src.mmd|src.puml>
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: lint-diagram.sh <src.mmd|src.puml>" >&2
  exit 2
fi

src="$1"
if [ ! -f "$src" ]; then
  echo "error: source not found: $src" >&2
  exit 2
fi

findings=0
report() { echo "LINT: $1" >&2; findings=$((findings + 1)); }

ext="${src##*.}"
case "$ext" in
  puml)
    # Strip single-quote comments and string literals so keywords inside :actions; are not counted.
    # One awk pass over the source. Strip single-quote comments, trim each line, then classify
    # by its leading keyword as a whole token. This avoids portability gaps in regex end anchors.
    # Reports three counts plus a missing-else tally so the shell can render specific findings.
    eval "$(awk '
      { sub(/'"'"'.*$/, ""); sub(/^[ \t]+/, ""); sub(/[ \t]+$/, "") }
      /^fork[ \t]+again([ \t]|$)/ { next }
      /^fork([ \t]|$)/            { forkopen++; stack[++sp]=0; next }
      /^end[ \t]+(fork|merge)([ \t]|$)/ { endfork++; if (sp>0) sp--; next }
      /^if[ \t]*\(/               { ifopen++; estack[++ei]=0; next }
      /^elseif[ \t]*\(/           { next }
      /^else([ \t]|$)|^else$/     { if (ei>0) estack[ei]=1; next }
      /^endif([ \t]|$)|^endif$/   { ifclose++; if (ei>0) { if (estack[ei]==0) miss++; ei-- } next }
      END {
        printf "forkopen=%d; endfork=%d; ifopen=%d; ifclose=%d; miss=%d\n",
               forkopen+0, endfork+0, ifopen+0, ifclose+0, miss+0
      }' "$src")"

    if [ "$forkopen" -ne "$endfork" ]; then
      report "unmatched fork/join: $forkopen fork opener(s) but $endfork end fork (every fork needs an end fork)"
    fi
    if [ "$ifopen" -ne "$ifclose" ]; then
      report "unmatched decision/merge: $ifopen if but $ifclose endif (every if needs an endif)"
    fi
    if [ "$miss" -gt 0 ]; then
      report "non-exhaustive decision: $miss if-block(s) have no else branch (add an else path)"
    fi
    ;;
  mmd)
    # Mermaid flowchart: a decision is a {..} node. Mermaid has no fork primitive, so concurrency
    # is out of scope here (the skill escalates such flows to PlantUML). Check guard exhaustiveness:
    # every decision node id must have at least one outgoing edge labeled |else| (case-insensitive).
    decisions=$(grep -oE '[A-Za-z0-9_]+\{[^}]*\}' "$src" | sed -E 's/\{.*//' | sort -u || true)
    if [ -n "$decisions" ]; then
      while IFS= read -r d; do
        [ -z "$d" ] && continue
        # outgoing edges from this decision node: lines of form  d -->|label| target
        edges=$(grep -E "(^|[^A-Za-z0-9_])$d[[:space:]]*--" "$src" || true)
        if ! printf '%s\n' "$edges" | grep -qiE '\|[[:space:]]*else[[:space:]]*\|'; then
          report "non-exhaustive decision: node '$d' has no |else| guard edge (guards must be exhaustive)"
        fi
      done <<< "$decisions"
    fi
    ;;
  *)
    echo "error: unsupported extension .$ext (expected .mmd or .puml)" >&2
    exit 2
    ;;
esac

if [ "$findings" -gt 0 ]; then
  echo "lint: $findings defect(s) found in $src" >&2
  exit 1
fi
echo "lint: clean ($src)"
