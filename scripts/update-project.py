#!/usr/bin/env python3
"""Record and update the Springer runtime inside a project instance.

A project instance carries a copy of the runtime (.claude/skills, agents,
references, hooks, and schemas) plus three files rendered from templates
(CLAUDE.md, .claude/settings.json, .gitignore). Until now a runtime change
reached an instance by hand, with rsync and a manual merge of the templates.
This script makes the copy an owned set: a manifest records every runtime
file the runtime owns with its content hash, so a later update can replace
what the instance never touched, keep what it edited, and say which is which.
Stdlib only.

Usage:
    python3 scripts/update-project.py manifest <target> --profile <profile>
    python3 scripts/update-project.py update <target> [--dry-run] [--force]
    python3 scripts/update-project.py status <target>

manifest  writes <target>/.claude/springer-manifest.json from the files now
          in the target. new-project.sh calls it after the initial copy.
update    brings the target up to this checkout. Per runtime file: added when
          new in the source, replaced when the target still matches the
          manifest, kept and reported when the target edited it (replaced
          only with --force), removed when gone from the source and unedited.
          A file the instance added under a runtime directory is kept. A
          template-rendered file is replaced when unedited, otherwise the new
          rendering is written beside it under .claude/springer-update/ for a
          hand merge. Refuses to touch a target with a live run lock unless
          --force, because a harness may be mid-tick.
status    prints what update would do, same as update --dry-run.

Exit 0 on success, 1 on a refusal or error, 2 on usage.
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
RUNTIME_DIRS = (".claude/skills", ".claude/agents", ".claude/references", ".claude/hooks", "schemas")
MANIFEST_REL = ".claude/springer-manifest.json"
UPDATE_DIR_REL = ".claude/springer-update"
PROFILES = ("brochure", "small", "saas", "mobile")
STALE_LOCK_SECONDS = 30 * 60
SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_SUFFIXES = {".pyc"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha256_text(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def runtime_files(root):
    """Every file under the runtime directories, as relative posix paths."""
    out = {}
    for rel_dir in RUNTIME_DIRS:
        base = root / rel_dir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_NAMES for part in path.parts) or path.suffix in SKIP_SUFFIXES:
                continue
            out[path.relative_to(root).as_posix()] = path
    return out


def render_claude_md(source, profile):
    """The same substitution new-project.sh applies with sed. The sentence sits
    mid-paragraph in the template, so the match is not anchored."""
    text = (source / "templates" / "project-CLAUDE.md").read_text()
    return text.replace("Default profile for this project: `saas`.",
                        f"Default profile for this project: `{profile}`.")


def render_gitignore(source):
    """Springer's .gitignore minus the rule that ignores the run store."""
    lines = (source / ".gitignore").read_text().splitlines(keepends=True)
    return "".join(l for l in lines
                   if l.rstrip("\n") != "/runs/" and not l.startswith("# --- Generated POC artifacts"))


def render_settings(source):
    return (source / "templates" / "project-settings.json").read_text()


def template_renders(source, profile):
    return {
        "CLAUDE.md": ("templates/project-CLAUDE.md", render_claude_md(source, profile)),
        ".claude/settings.json": ("templates/project-settings.json", render_settings(source)),
        ".gitignore": (".gitignore", render_gitignore(source)),
    }


def source_commit(source):
    try:
        return subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_manifest(target, source, profile, previous=None):
    manifest = {
        "springer_manifest": 1,
        "source_commit": source_commit(source),
        "profile": profile,
        "created_at": (previous or {}).get("created_at") or utc_now(),
        "updated_at": utc_now(),
        "runtime": {rel: sha256(path) for rel, path in runtime_files(target).items()},
        "templates": {},
    }
    # A template-rendered file is measured against the pristine render at this
    # source, never against whatever the instance holds. Recording the current
    # file as owned would let a later update replace an instance's own
    # gitignore or settings additions. A file that differs from the render at
    # adoption is therefore treated as edited until an update rewrites it.
    for rel, (from_rel, rendered) in template_renders(source, profile).items():
        manifest["templates"][rel] = {
            "from": from_rel,
            "rendered_hash": sha256_text(rendered),
        }
    return manifest


def load_manifest(target):
    path = target / MANIFEST_REL
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_manifest(target, manifest):
    path = target / MANIFEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def live_locks(target):
    """Run directories whose .lock heartbeat is still fresh."""
    live = []
    for lock in (target / "runs").glob("*/.lock"):
        try:
            data = json.loads(lock.read_text())
            claimed = time.mktime(time.strptime(data.get("claimed_at", ""), "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if time.time() - claimed < STALE_LOCK_SECONDS:
            live.append(f"{lock.parent.name} (session {data.get('session_id')})")
    return live


def plan_update(target, source, manifest):
    """Decide what to do with every file. Returns a dict of lists keyed by
    action, each entry a relative path (plus a reason where useful)."""
    plan = {"add": [], "replace": [], "unchanged": [], "keep_modified": [],
            "remove": [], "keep_modified_removed": [], "keep_instance_only": [],
            "template_replace": [], "template_unchanged": [], "template_merge": []}
    recorded = manifest.get("runtime", {})
    src_files = runtime_files(source)
    tgt_files = runtime_files(target)
    src_hashes = {rel: sha256(path) for rel, path in src_files.items()}

    for rel, src_hash in src_hashes.items():
        if rel not in tgt_files:
            plan["add"].append(rel)
            continue
        tgt_hash = sha256(tgt_files[rel])
        if tgt_hash == src_hash:
            plan["unchanged"].append(rel)
        elif rel in recorded and tgt_hash == recorded[rel]:
            plan["replace"].append(rel)
        else:
            plan["keep_modified"].append(rel)

    for rel in tgt_files:
        if rel in src_hashes:
            continue
        if rel in recorded:
            if sha256(tgt_files[rel]) == recorded[rel]:
                plan["remove"].append(rel)
            else:
                plan["keep_modified_removed"].append(rel)
        else:
            plan["keep_instance_only"].append(rel)

    profile = manifest.get("profile") or "saas"
    for rel, (_, rendered) in template_renders(source, profile).items():
        path = target / rel
        record = manifest.get("templates", {}).get(rel) or {}
        new_hash = sha256_text(rendered)
        current = sha256(path) if path.exists() else None
        if current == new_hash:
            plan["template_unchanged"].append(rel)
        elif current is None or current == record.get("rendered_hash"):
            plan["template_replace"].append(rel)
        else:
            plan["template_merge"].append(rel)
    return plan


def apply_update(target, source, manifest, plan, force):
    src_files = runtime_files(source)
    for rel in plan["add"] + plan["replace"] + (plan["keep_modified"] if force else []):
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src_files[rel].read_bytes())
        dest.chmod(src_files[rel].stat().st_mode & 0o777)
    for rel in plan["remove"] + (plan["keep_modified_removed"] if force else []):
        (target / rel).unlink()
    profile = manifest.get("profile") or "saas"
    renders = template_renders(source, profile)
    for rel in plan["template_replace"] + (plan["template_merge"] if force else []):
        (target / rel).write_text(renders[rel][1])
    if not force:
        update_dir = target / UPDATE_DIR_REL
        for rel in plan["template_merge"]:
            out = update_dir / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(renders[rel][1])


def print_plan(plan, dry_run, force):
    labels = [
        ("add", "added"),
        ("replace", "replaced (unedited since the manifest)"),
        ("remove", "removed (gone from the source, unedited)"),
        ("keep_modified", "edited in the instance, kept" + (" (replaced: --force)" if force else "")),
        ("keep_modified_removed", "gone from the source but edited here, kept" + (" (removed: --force)" if force else "")),
        ("keep_instance_only", "added by the instance, kept"),
        ("template_replace", "template render replaced (unedited)"),
        ("template_merge", "template changed and the file was edited: new render under "
                           f"{UPDATE_DIR_REL}/ for a hand merge" + (" (overwritten: --force)" if force else "")),
    ]
    verb = "would be" if dry_run else "were"
    for key, label in labels:
        items = plan[key]
        if not items:
            continue
        print(f"{len(items)} {label}")
        for rel in items:
            print(f"  {rel}")
    print(f"{len(plan['unchanged'])} runtime files and {len(plan['template_unchanged'])} "
          f"template renders already match. Files {verb} written as listed."
          if not dry_run else
          f"{len(plan['unchanged'])} runtime files and {len(plan['template_unchanged'])} "
          f"template renders already match. Dry run, nothing written.")


def cmd_manifest(target, profile):
    if profile not in PROFILES:
        sys.stderr.write(f"profile must be one of {', '.join(PROFILES)}\n")
        return 2
    manifest = build_manifest(target, SOURCE, profile, load_manifest(target))
    write_manifest(target, manifest)
    print(f"wrote {MANIFEST_REL}: {len(manifest['runtime'])} runtime files, "
          f"source {manifest['source_commit'] or 'unknown'}")
    # Adopting an instance that was synced by hand: anything that already
    # differs from this checkout is recorded as owned as it stands, so the
    # next update will replace it. Say so, so a local edit is not lost unseen.
    src = {rel: sha256(path) for rel, path in runtime_files(SOURCE).items()}
    differing = sorted(rel for rel, h in manifest["runtime"].items() if rel in src and src[rel] != h)
    if differing:
        print(f"{len(differing)} runtime file(s) differ from this checkout and are recorded as "
              "owned as they stand. The next update replaces them. Review before updating "
              "if any carries a local edit:")
        for rel in differing:
            print(f"  {rel}")
    edited_templates = sorted(
        rel for rel, (_, rendered) in template_renders(SOURCE, profile).items()
        if (target / rel).exists() and sha256(target / rel) != sha256_text(rendered))
    if edited_templates:
        print(f"{len(edited_templates)} template-rendered file(s) differ from the render and are "
              "treated as edited. An update writes the new render beside them under "
              f"{UPDATE_DIR_REL}/ for a hand merge:")
        for rel in edited_templates:
            print(f"  {rel}")
    return 0


def cmd_update(target, dry_run, force):
    manifest = load_manifest(target)
    if manifest is None:
        sys.stderr.write(f"{target} has no {MANIFEST_REL}. Create one with the manifest "
                         "command (it records the current files as owned) and rerun.\n")
        return 1
    locks = live_locks(target)
    if locks and not force:
        sys.stderr.write("refusing: a harness holds a live lock on " + ", ".join(locks)
                         + ". Wait for it to release, or pass --force.\n")
        return 1
    plan = plan_update(target, SOURCE, manifest)
    print_plan(plan, dry_run, force)
    if dry_run:
        return 0
    apply_update(target, SOURCE, manifest, plan, force)
    write_manifest(target, build_manifest(target, SOURCE, manifest.get("profile") or "saas", manifest))
    print(f"manifest refreshed at source {source_commit(SOURCE) or 'unknown'}")
    return 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = [a for a in argv[1:] if a.startswith("--")]
    if len(args) < 2 or args[0] not in ("manifest", "update", "status"):
        sys.stderr.write(__doc__)
        return 2
    target = Path(args[1]).resolve()
    if not target.is_dir():
        sys.stderr.write(f"no such directory: {target}\n")
        return 1
    if args[0] == "manifest":
        profile = None
        if "--profile" in argv:
            i = argv.index("--profile")
            profile = argv[i + 1] if i + 1 < len(argv) else None
        if not profile:
            sys.stderr.write("manifest needs --profile <brochure|small|saas|mobile>\n")
            return 2
        return cmd_manifest(target, profile)
    dry_run = args[0] == "status" or "--dry-run" in flags
    return cmd_update(target, dry_run, "--force" in flags)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
