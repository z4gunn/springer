"""Risk levels as static, auditable data. Rules raise a level and never lower one."""

import re

LEVELS = ("L0", "L1", "L2", "L3")
L2_PATHS = {
    "auth": r"(^|/)(auth|authn|authz|session|sessions|permissions?|rbac|roles?|oauth|identity|login|sso)(/|\.|_|-)",
    "tenancy": r"(^|/)(tenants?|tenancy|organi[sz]ations?)(/|\.|_|-)",
    "migration": r"(^|/)migrations?/|(^|/)drizzle/|\.sql$",
    "payments": r"(^|/)(billing|payments?|stripe|checkout|subscriptions?|invoices?|entitlements?)(/|\.|_|-)",
    "secrets": r"(^|/)\.env[^/]*$|(^|/)secrets?/",
    "uploads": r"(^|/)uploads?(/|\.|_|-)",
    "dependency": r"(^|/)(package\.json|pnpm-lock\.yaml|requirements[^/]*\.txt|pyproject\.toml)$",
    "conventions": r"(^|/)\.github/workflows/|(^|/)packages/(config|conventions)/|(^|/)Dockerfile[^/]*$",
}
_COMPILED = {name: re.compile(pattern) for name, pattern in L2_PATHS.items()}


def triggers(paths):
    return sorted({name for path in paths for name, rule in _COMPILED.items() if rule.search(path)})


def raise_level(*levels):
    return max((level for level in levels if level), key=LEVELS.index)


PLAN_REASONS = ("auth", "data-model", "billing", "vendor", "infra", "irreversible")


def baseline_for(baseline, reason=None):
    """The plan's L2 stands only with a reason from the gate list. Without one the files
    the change touched decide, so a blanket L2 never holds an ordinary merge for a person."""
    return "L1" if baseline == "L2" and reason not in PLAN_REASONS else baseline


def level_for(paths, baseline, reviewer=None, reason=None):
    return raise_level(baseline_for(baseline, reason), "L2" if triggers(paths) else "L0", reviewer)
