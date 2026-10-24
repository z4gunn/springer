#!/usr/bin/env python3
"""Decide whether a pull request merges on its own or waits for the human.

The pr-merge gate used to fire per batch on every saas and mobile run, so an
unattended run spent most of its wall clock waiting for a merge nobody was
there to make. Most PRs carry no decision a human must take: the reviewer
approved them, the receipts hold, CI is green. This script reads what a PR
changes and names its risk. Low and medium merge automatically once the merge
bar holds. High stops at a pr-merge gate that holds only the work that
depends on it. Stdlib only.

High, each a category the human reviews:
  auth       authentication, sessions, permissions, roles, identity
  data       the data model, a migration, or a destructive statement (DROP,
             RENAME, DELETE FROM, TRUNCATE) in an added line
  money      billing, payments, subscriptions, invoices, entitlements
  vendor     a new dependency on a vendor SDK that becomes a sub-processor
  infra      CI and CD pipelines, IaC, containers, deploy config, secrets and
             environment files
  security   an open Critical or High finding in an audit artifact passed in
  fact       a `TODO(DEF-<n>)` placeholder, a fact only the human can supply
Medium: a dependency change, an accepted gate-integrity tag that removed or
skipped a test or loosened a check, or a diff over 400 changed lines.
Low: everything else.

A project overrides or extends the path rules in `runs/_risk.json`:
    {"high": {"auth": ["^src/server/session/"]}, "low": ["^docs/", "^copy/"]}
A `low` prefix exempts a path from every path rule, never from a security
finding or a placeholder.

Usage:
    pr-risk.py <base> <head> [--repo <path>] [--tags <review.md.tags.json>]
               [--review <code-review.json>] [--audit <artifact.json>...]
               [--config <runs/_risk.json>] [--out <file>]

Prints one JSON object: the risk, the categories, and one reason per line
that set it. Exit 0 when the PR may merge on its own (low or medium), 1 when
it is high, 2 on usage or a git error.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HIGH_PATHS = {
    "auth": [r"(^|/)(auth|authn|authz|session|sessions|permission|permissions|rbac|roles?|oauth|identity|login|sso)(/|\.|_|-)",
             r"(^|/)middleware/(auth|session)"],
    "data": [r"(^|/)migrations?/", r"(^|/)schema\.prisma$", r"(^|/)drizzle/", r"(^|/)alembic/",
             r"\.sql$", r"(^|/)(models?|entities)/"],
    "money": [r"(^|/)(billing|payments?|stripe|checkout|subscriptions?|invoices?|pricing|entitlements?)(/|\.|_|-)"],
    "infra": [r"(^|/)\.github/workflows/", r"(^|/)\.gitlab-ci\.ya?ml$", r"(^|/)Dockerfile[^/]*$",
              r"(^|/)docker-compose[^/]*\.ya?ml$", r"\.tf$", r"(^|/)(terraform|pulumi|infra|iac|k8s|helm|deploy)/",
              r"(^|/)(vercel|netlify|fly|render|railway)\.(json|toml|ya?ml)$", r"(^|/)wrangler\.toml$",
              r"(^|/)\.env[^/]*$", r"(^|/)secrets?/", r"(^|/)Procfile$"],
}
DESTRUCTIVE = re.compile(r"\b(DROP\s+(TABLE|COLUMN|INDEX|SCHEMA|DATABASE)|RENAME\s+(TO|COLUMN)|DELETE\s+FROM|TRUNCATE)\b"
                         r"|\.(dropTable|dropColumn|renameColumn|renameTable)\(|op\.drop_", re.I)
PLACEHOLDER = re.compile(r"TODO\(DEF-\d+\)")
MANIFESTS = re.compile(r"(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|Pipfile|go\.mod|Cargo\.toml|"
                       r"Gemfile|composer\.json|pubspec\.yaml|build\.gradle(\.kts)?|Podfile)$")
VENDORS = re.compile(r"\b(stripe|braintree|paddle|twilio|sendgrid|@sendgrid|mailgun|postmark|resend|aws-sdk|@aws-sdk|"
                     r"boto3|@google-cloud|google-cloud|firebase|@supabase|supabase|auth0|@clerk|clerk|okta|"
                     r"segment|@segment|mixpanel|amplitude|posthog|sentry|@sentry|datadog|openai|anthropic|"
                     r"@anthropic-ai|cohere|algolia|plaid|intercom|hubspot|salesforce)\b", re.I)
EASING_TAGS = {"TEST-REMOVED", "TEST-SKIPPED", "ASSERTION-LOSS", "CHECK-CONFIG", "SUPPRESSION", "GOLDEN-EDITED"}
SIZE_LIMIT = 400


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or f"git {' '.join(args)} failed")
    return p.stdout


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def open_blocking_findings(artifact):
    """Critical or High findings an audit artifact still reports open, or a
    GATE verdict. Shapes vary by vertical, so walk the content."""
    content = (artifact or {}).get("content", artifact or {})
    hits = []
    if str(content.get("verdict", "")).upper() == "GATE":
        hits.append("audit verdict GATE")

    def walk(node):
        if isinstance(node, dict):
            sev = str(node.get("severity", "")).lower()
            status = str(node.get("status", "open")).lower()
            if sev in ("critical", "high") and status not in ("resolved", "fixed", "closed", "accepted"):
                hits.append(f"{sev} finding: {str(node.get('title') or node.get('description') or '')[:100]}")
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(content.get("findings", []))
    return hits


def assess(repo, base, head, tags=None, review=None, audits=(), config=None):
    config = config or {}
    high_paths = {k: list(v) for k, v in HIGH_PATHS.items()}
    for cat, patterns in (config.get("high") or {}).items():
        high_paths.setdefault(cat, []).extend(patterns)
    low = [re.compile(p) for p in config.get("low", [])]
    reasons = {"high": [], "medium": []}

    files = [l for l in git(repo, "diff", "--name-only", "--no-renames", f"{base}...{head}").splitlines() if l]
    diff = git(repo, "diff", "-U0", "--no-renames", f"{base}...{head}")
    changed = sum(int(a) + int(d) for a, d, *_ in
                  (l.split("\t") for l in git(repo, "diff", "--numstat", f"{base}...{head}").splitlines())
                  if a.isdigit() and d.isdigit())

    for path in files:
        if any(r.search(path) for r in low) or path.startswith("runs/"):
            continue
        for cat, patterns in high_paths.items():
            if any(re.search(p, path, re.I) for p in patterns):
                reasons["high"].append((cat, f"{path} is a {cat} path"))
                break
        if MANIFESTS.search(path):
            reasons["medium"].append(("dependency", f"{path} changes dependencies"))

    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
            continue
        if not line.startswith("+") or line.startswith("+++") or current is None:
            continue
        if current.startswith("runs/"):
            continue
        text = line[1:]
        if DESTRUCTIVE.search(text):
            reasons["high"].append(("data", f"{current}: destructive statement `{text.strip()[:80]}`"))
        if PLACEHOLDER.search(text):
            reasons["high"].append(("fact", f"{current}: placeholder {PLACEHOLDER.search(text).group(0)}"))
        if MANIFESTS.search(current) and VENDORS.search(text):
            reasons["high"].append(("vendor", f"{current}: new vendor dependency `{text.strip()[:80]}`"))

    if changed > SIZE_LIMIT:
        reasons["medium"].append(("size", f"{changed} changed lines, over {SIZE_LIMIT}"))
    given = {}
    if review:
        content = review.get("content", review)
        given = {d.get("id"): d for d in content.get("gate_tags", []) if isinstance(d, dict)}
    for t in tags or []:
        if t.get("tag") in EASING_TAGS and given.get(t.get("id"), {}).get("disposition") != "finding":
            reasons["medium"].append(("gate-tag", f"{t.get('id')} {t.get('tag')} {t.get('file') or ''} accepted"))
    for artifact in audits:
        for hit in open_blocking_findings(artifact):
            reasons["high"].append(("security", hit))

    risk = "high" if reasons["high"] else "medium" if reasons["medium"] else "low"
    categories = sorted({c for c, _ in reasons["high"]} if reasons["high"] else {c for c, _ in reasons["medium"]})
    seen, lines = set(), []
    for level in ("high", "medium"):
        for cat, why in reasons[level]:
            if why not in seen:
                seen.add(why)
                lines.append(f"{level} {cat}: {why}")
    return {"risk": risk, "auto_merge": risk != "high", "categories": categories,
            "changed_lines": changed, "files": len(files), "reasons": lines}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--tags")
    ap.add_argument("--review")
    ap.add_argument("--audit", nargs="*", default=[])
    ap.add_argument("--config")
    ap.add_argument("--out")
    a = ap.parse_args(argv[1:])
    config_path = Path(a.config) if a.config else Path(a.repo) / "runs" / "_risk.json"
    try:
        result = assess(a.repo, a.base, a.head,
                        tags=load_json(a.tags) if a.tags else None,
                        review=load_json(a.review) if a.review else None,
                        audits=[x for x in (load_json(p) for p in a.audit) if x],
                        config=load_json(config_path) if config_path.exists() else None)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"pr-risk: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2)
    if a.out:
        Path(a.out).write_text(text + "\n")
    print(text)
    return 0 if result["auto_merge"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
