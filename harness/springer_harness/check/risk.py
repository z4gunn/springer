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


def level_for(paths, baseline, reviewer=None):
    return raise_level(baseline, "L2" if triggers(paths) else "L0", reviewer)
