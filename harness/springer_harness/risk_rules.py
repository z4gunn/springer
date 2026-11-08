"""A gate answer's rule change, applied to the project's risk rules.

pr-risk.py reads `runs/_risk.json`: `{"high": {"<category>": ["<regex>", ...]}, "low": ["<regex>", ...]}`.
A rule change is one line, `low <regex>` to exempt matching paths from every path rule,
or `high <category> <regex>` to make matching paths high risk. Approving with a rule
change is how autonomy grows without lowering the bar (design-notes, Vertical review).
"""

import re
from pathlib import Path

from .common import read_json, write_json

FILE = "runs/_risk.json"
SYNTAX = "a rule change is `low <regex>` or `high <category> <regex>`"


def parse(text):
    """The rule as (kind, category, pattern), or ValueError naming the syntax."""
    words = (text or "").strip().split(None, 2)
    if len(words) == 2 and words[0] == "low":
        kind, category, pattern = "low", None, words[1]
    elif len(words) == 3 and words[0] == "high" and re.fullmatch(r"[a-z][a-z0-9_-]*", words[1]):
        kind, category, pattern = "high", words[1], words[2].strip()
    else:
        raise ValueError(SYNTAX)
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"the pattern does not compile: {exc}") from exc
    return kind, category, pattern


def apply(project, text):
    """Merge the rule into the project's rules file. True when the file changed."""
    kind, category, pattern = parse(text)
    path = Path(project) / FILE
    rules = read_json(path) or {}
    if kind == "low":
        target = rules.setdefault("low", [])
    else:
        target = rules.setdefault("high", {}).setdefault(category, [])
    if pattern in target:
        return False
    target.append(pattern)
    write_json(path, rules)
    return True
