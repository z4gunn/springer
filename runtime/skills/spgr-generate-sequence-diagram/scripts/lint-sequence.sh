#!/usr/bin/env bash
# Structural balance lint for sequence-diagram source. Catches the failure modes that a
# renderer passes silently or reports with an unhelpful stack trace:
#   - every combined fragment (alt, opt, loop, par, critical, break, group, box, rect)
#     must close with a matching end
#   - every explicit activate must have a matching deactivate
# A Mermaid activate without a deactivate renders clean SVG with a bar that never closes,
# so the renderer alone cannot catch it. A PlantUML fragment left open is swallowed by
# @enduml. This lint is the structural gate; render-sequence.sh is the parse gate.
#
# Activation counted here is the explicit activate / deactivate keyword only. The Mermaid
# +/- arrow suffix and PlantUML autoactivate self-balance and are not counted.
#
# Usage: lint-sequence.sh <file.mmd | file.puml> [more files ...]
# Exit 0 = all files balanced. Exit 1 = at least one imbalance. Exit 2 = usage error.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: lint-sequence.sh <file.mmd | file.puml> [more files ...]" >&2
  exit 2
fi

status=0

# Strip comments and inline message text so a keyword inside a label is not miscounted.
# Mermaid comment: a line whose first non-space chars are %%. PlantUML comment: leading '.
# Message text after the first colon is dropped, since "alt" inside a label is not a block.
strip() {
  sed -e 's/%%.*$//' -e 's/^[[:space:]]*'\''.*$//' -e 's/:.*$//'
}

# Count leading-keyword occurrences. A fragment opener or activate keyword must be the
# first token on its (stripped) line, so an "end" inside a participant name is ignored.
count_kw() {
  # $1 = file, $2 = extended regex anchored at line start after optional indentation
  strip < "$1" | grep -E -c "^[[:space:]]*($2)([[:space:]]|\$)" || true
}

for f in "$@"; do
  if [ ! -f "$f" ]; then
    echo "FAIL $f: not found" >&2
    status=1
    continue
  fi

  openers=$(count_kw "$f" "alt|opt|loop|par|critical|break|group|box|rect")
  ends=$(count_kw "$f" "end")
  acts=$(count_kw "$f" "activate")
  deacts=$(count_kw "$f" "deactivate")

  file_ok=1

  if [ "$openers" -ne "$ends" ]; then
    echo "FAIL $f: $openers fragment opener(s) (alt/opt/loop/par/critical/break/group/box/rect) but $ends end(s)" >&2
    grep -E -n "^[[:space:]]*(alt|opt|loop|par|critical|break|group|box|rect)([[:space:]]|$)" "$f" >&2 || true
    file_ok=0
  fi

  if [ "$acts" -ne "$deacts" ]; then
    echo "FAIL $f: $acts activate(s) but $deacts deactivate(s) (a Mermaid bar that never closes renders silently)" >&2
    grep -E -n "^[[:space:]]*(de)?activate([[:space:]]|$)" "$f" >&2 || true
    file_ok=0
  fi

  if [ "$file_ok" -eq 1 ]; then
    echo "OK   $f: $openers fragment(s) balanced, $acts explicit activation(s) balanced"
  else
    status=1
  fi
done

exit "$status"
