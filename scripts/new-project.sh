#!/usr/bin/env bash
#
# new-project.sh - instantiate a new Springer-driven application project.
#
# Springer is a workspace: the file-writing tooling is bound to the repository
# root, and the schema registry and shared references are cited by repo-relative
# path. So each application is built inside its own copy of the Springer runtime.
# This script lays down that copy in a target directory, which becomes the app's
# own git repository.
#
# Usage: scripts/new-project.sh <target-dir> [profile]
#
# The target directory must not already exist or must be empty. The script copies
# the runtime subset (.claude/skills, .claude/agents, .claude/references, schemas),
# installs the downstream project ruleset as CLAUDE.md, seeds an empty run store,
# and initializes a git repository with one commit.
#
# profile is the default run profile written into CLAUDE.md: brochure, small,
# saas (the default), or mobile. See the run-profiles table in
# .claude/references/pdca-harness.md.

set -euo pipefail

usage() {
  echo "Usage: $(basename "$0") <target-dir> [brochure|small|saas|mobile]" >&2
  echo "Create a new Springer-driven project at <target-dir>." >&2
  exit 2
}

[ $# -ge 1 ] && [ $# -le 2 ] || usage
TARGET="$1"
PROFILE="${2:-saas}"
case "$PROFILE" in
  brochure|small|saas|mobile) ;;
  *) echo "Error: unknown profile '$PROFILE'." >&2; usage ;;
esac

# Resolve the Springer source root from this script's own location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$SCRIPT_DIR/.." && pwd)"

# Refuse to overwrite a non-empty target.
if [ -e "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null || true)" ]; then
  echo "Error: target '$TARGET' exists and is not empty. Choose a new path." >&2
  exit 1
fi

mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"

if [ ! -f "$SRC/templates/project-CLAUDE.md" ]; then
  echo "Error: cannot find Springer runtime at '$SRC'. Run this script from its repo." >&2
  exit 1
fi

echo "Creating Springer project at $TARGET"
echo "  source: $SRC"

# 1. Copy the runtime subset. Exclude the build-only and workspace pieces:
#    .claude/workflows (the scripts that built Springer), templates, .venv,
#    .git, README.md, and any existing run output.
mkdir -p "$TARGET/.claude"
cp -R "$SRC/.claude/skills"     "$TARGET/.claude/skills"
cp -R "$SRC/.claude/agents"     "$TARGET/.claude/agents"
cp -R "$SRC/.claude/references" "$TARGET/.claude/references"
cp -R "$SRC/.claude/hooks"      "$TARGET/.claude/hooks"
cp "$SRC/.claude/settings.json" "$TARGET/.claude/settings.json"
cp -R "$SRC/schemas"            "$TARGET/schemas"

# 2. Install the downstream ruleset as the project's CLAUDE.md, stamping the
#    default run profile.
sed "s/^Default profile for this project: \`saas\`\./Default profile for this project: \`$PROFILE\`./" \
  "$SRC/templates/project-CLAUDE.md" > "$TARGET/CLAUDE.md"

# 3. Derive a .gitignore from Springer's, minus the rule that ignores the run
#    store. In an application project the run artifacts are the design record and
#    are tracked, so the "/runs/" ignore and its comment are dropped.
grep -v -e '^/runs/$' -e '^# --- Generated POC artifacts' "$SRC/.gitignore" > "$TARGET/.gitignore"

# 4. Seed an empty run store so the directory exists in the first commit.
mkdir -p "$TARGET/runs"
touch "$TARGET/runs/.gitkeep"

# 5. Initialize the project repository with one commit.
git -C "$TARGET" init -q
git -C "$TARGET" add -A
git -C "$TARGET" -c user.name='Springer' -c user.email='springer@local' \
  commit -q -m "chore: scaffold Springer project"

cat <<EOF

Done. Next steps:

  cd $TARGET
  claude

Then describe the app you want to build and delegate to the Orchestrator agent
(spgr-agent-orchestrator), or start with spgr-agent-discovery. The run profile is
$PROFILE. Put a "profile: $PROFILE" line in the run's problem statement. The
team pauses at the five human checkpoints: architecture approval,
design-direction selection, pull-request merge, a security or compliance flag,
and a scope change.

Artifacts accumulate under runs/<run-id>/. Application source code is written into
the project tree.
EOF
