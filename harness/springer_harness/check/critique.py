"""Check brief: the critique rules in the design notes. An error blocks run.start,
a warning shows inline, and an info line becomes an intake question."""

import re

from ..state.brief import REQUIRED, derive

PINNED_IDS = {"hosting", "db", "orm", "auth", "api", "jobs", "realtime", "billing", "email", "storage", "analytics",
              "errors", "tenancy"}
MAX_FLOW_STEPS = 12


def parse_flows(text):
    """Each flow is a ### heading followed by `Field: value` lines and numbered steps."""
    flows = []
    for block in re.split(r"(?m)^### ", text or "")[1:]:
        name, _, rest = block.partition("\n")
        fields = {m.group(1).lower(): m.group(2).strip()
                  for m in re.finditer(r"(?m)^(Who|Trigger|Outcome|Critical|Surface):[ \t]*(.*)$", rest)}
        steps = len(re.findall(r"(?m)^\s*\d+\.\s", rest))
        flows.append({"name": name.strip(), "steps": steps, **fields})
    return flows


def parse_users(text):
    names = re.findall(r"(?m)^(?:### |- )([^:\n]+)", text or "")
    return {n.strip().lower() for n in names}


def critique(front, sections):
    errors, warnings, info = [], [], []

    def add(bucket, rule, section, message):
        bucket.append({"rule": rule, "section": section, "message": message})

    proposed = set(front.get("proposed") or [])
    for name in REQUIRED:
        if name == "Non-goals":
            continue
        if not sections.get(name):
            add(errors, "missing-section", name, f"{name} is required.")
    for name in REQUIRED:
        if name in proposed:
            add(errors, "unconfirmed-section", name, f"{name} is still a proposal. Confirm or edit it.")
    flows = parse_flows(sections.get("Core flows"))
    if sections.get("Core flows") and not flows:
        add(errors, "flows-not-structured", "Core flows",
            "Core flows is prose, and each flow becomes an epic, so it needs its fields. Start each flow with a "
            "### heading, then Who:, Trigger:, numbered steps, Outcome:, and Critical: yes or no.")
    users = parse_users(sections.get("Users"))
    surfaces = front.get("surfaces") or []
    for flow in flows:
        if not flow.get("outcome"):
            add(errors, "flow-without-outcome", "Core flows", f"{flow['name']} has no outcome.")
        who = (flow.get("who") or "").lower()
        if who and who not in users:
            add(errors, "unknown-user", "Core flows", f"{flow['name']} names {flow['who']}, who is not in Users. Add them to Users.")
        if flow.get("surface") and flow["surface"] not in surfaces:
            add(errors, "surface-contradiction", "Core flows",
                f"{flow['name']} runs on {flow['surface']}, which is not a surface of this product.")
        if flow["steps"] > MAX_FLOW_STEPS:
            add(warnings, "long-flow", "Core flows", f"{flow['name']} has {flow['steps']} steps. Split it.")
    if flows and not any((f.get("critical") or "").lower() in ("yes", "true") for f in flows):
        add(errors, "no-critical-flow", "Core flows", "No flow is marked critical.")
    pinned = front.get("pinned") or {}
    for key in sorted(set(pinned) - PINNED_IDS):
        add(errors, "unknown-pinned-key", "Facts", f"{key} is not a pinned decision id.")
    if not sections.get("Non-goals"):
        add(warnings, "no-non-goals", "Non-goals", "Name what the first version will not build.")
    if not sections.get("Success criteria"):
        add(warnings, "no-success-criteria", "Success criteria", "Name how you will know it worked.")
    if front.get("deploy") == "self-hosted" and "supabase" in str(pinned.get("db", "")).lower():
        add(warnings, "pin-conflicts-with-deploy", "Facts", "Supabase on self-hosted is heavy.")
    if front.get("variants") and derive(front)["profile"] == "brochure":
        add(warnings, "variants-on-brochure", "Facts", "Variants are off by default on a brochure.")
    for mention in re.findall(r"docs/inputs/[\w./-]+", sections.get("Inputs and references", "")):
        add(info, "input-not-present", "Inputs and references", f"{mention} becomes an intake question.")
    return {"errors": errors, "warnings": warnings, "info": info}
