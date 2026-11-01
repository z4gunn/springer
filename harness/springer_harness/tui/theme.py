"""The look, called Lintel, from the arch in brand/springer-icon.svg. Everything is
stone. Terracotta, the color of the icon's two springers, means one thing: this needs
you. Every color a pane uses comes from here, so the rule holds in one place and the
light and dark variants cannot drift apart.
"""

import os

from rich.text import Text
from textual.theme import Theme

DARK = {"text": "#E4DED2", "dim": "#7D786E", "stone": "#B7AE9E", "you": "#E08A5A", "you_bar": "#C26A3C",
        "selected": "#1E2024", "card": "#25221E", "border": "#3A3833", "error": "#D9694F", "success": "#8FA876",
        "background": "#16171A", "surface": "#1E2024"}
LIGHT = {"text": "#2A2620", "dim": "#6E675A", "stone": "#5F584C", "you": "#A8521F", "you_bar": "#C26A3C",
         "selected": "#EFEAE0", "card": "#F6EEE6", "border": "#D8D2C6", "error": "#B8432C", "success": "#4F7A3A",
         "background": "#FBF9F5", "surface": "#F3F0EA"}
# The icon's own stones, the same on either background.
MARK_RING, MARK_SPRINGER, MARK_PIER = "#CFC7B8", "#C26A3C", "#B7AE9E"
MARK = (".SSSSSS.", "SS....SS", "TT....TT", "PP....PP")


def is_light():
    """SPRINGER_THEME wins. Otherwise COLORFGBG, which many terminals set, names the
    background. With neither, dark."""
    explicit = os.environ.get("SPRINGER_THEME", "").lower()
    if explicit in ("light", "dark"):
        return explicit == "light"
    background = os.environ.get("COLORFGBG", "").rsplit(";", 1)[-1]
    return background in ("7", "15")


C = LIGHT if is_light() else DARK

THEME = Theme(name="springer", dark=C is DARK, primary=C["you_bar"], secondary=C["stone"], accent=C["you_bar"],
              warning=C["you"], error=C["error"], success=C["success"], foreground=C["text"],
              background=C["background"], surface=C["surface"], panel=C["selected"])

RISK = {"L0": "dim", "L1": "stone", "L2": "you", "L3": "error"}
COLUMN = {"ready": "dim", "in_progress": "text", "in_review": "stone", "blocked": "error", "done": "success"}

# Nine stones: brief, requirements, direction, scope, the keystone (the walking skeleton),
# three of features, release. The value is how many are laid when a run is in that phase.
STONES = 9
STONES_LAID = {"requirements": 1, "direction": 2, "structure": 3, "design-system": 3, "scope": 3, "skeleton": 4,
               "development": 5, "features": 5, "release": 8, "retrospective": 9}


def stones_laid(phase, complete=False):
    """A phase this table does not know shows no count rather than a wrong one."""
    return STONES if complete else STONES_LAID.get(phase)


def paint(text, color=None, bold=False):
    style = " ".join(x for x in ("bold" if bold else "", C[color] if color else "") if x)
    return Text(str(text), style=style)


def join(*parts):
    """Assemble painted parts and plain strings into one Text."""
    return Text.assemble(*[p if isinstance(p, Text) else Text(str(p)) for p in parts])


def lines(rows):
    return Text("\n").join(rows)


def keys(*pairs):
    """A hint row: each key bright, what it does gray. Terracotta is kept for what
    needs a person, so a key that is merely available stays out of it."""
    parts = []
    for index, (key, label) in enumerate(pairs):
        if index:
            parts.append("   ")
        parts += [paint(key, "text", bold=True), paint(f" {label}", "dim")]
    return join(*parts)


def mark():
    """The arch in two terminal lines, each cell two square pixels."""
    colors = {"S": MARK_RING, "T": MARK_SPRINGER, "P": MARK_PIER}
    rows = []
    for top, bottom in ((MARK[0], MARK[1]), (MARK[2], MARK[3])):
        row = Text()
        for upper, lower in zip(top, bottom):
            a, b = colors.get(upper), colors.get(lower)
            if a and b:
                row.append("▀", style=f"{a} on {b}")
            elif a:
                row.append("▀", style=a)
            elif b:
                row.append("▄", style=b)
            else:
                row.append(" ")
        rows.append(row)
    return lines(rows)
