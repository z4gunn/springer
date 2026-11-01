"""The look: warm text, one amber accent, and state shown by tint rather than boxes.
Takes its palette direction from OpenClaw's terminal UI. Every color a pane uses comes
from here, so the light and dark variants cannot drift apart.
"""

import os

from rich.text import Text
from textual.theme import Theme

DARK = {"text": "#E8E3D5", "dim": "#7B7F87", "accent": "#F6C453", "soft": "#F2A65A", "border": "#3C414B",
        "selected": "#2B2F36", "system": "#9BA3B2", "pending": "#1F2A2F", "ok_bg": "#1E2D23", "error_bg": "#2F1F1F",
        "error": "#F97066", "success": "#7DD3A5", "background": "#14161A", "surface": "#1B1E24"}
LIGHT = {"text": "#1E1E1E", "dim": "#5B6472", "accent": "#B45309", "soft": "#C2410C", "border": "#C9CDD4",
         "selected": "#F3F0E8", "system": "#4B5563", "pending": "#EFF6FF", "ok_bg": "#ECFDF5", "error_bg": "#FEF2F2",
         "error": "#DC2626", "success": "#047857", "background": "#FFFFFF", "surface": "#FAF8F3"}


def is_light():
    """SPRINGER_THEME wins. Otherwise COLORFGBG, which many terminals set, names the
    background. With neither, dark."""
    explicit = os.environ.get("SPRINGER_THEME", "").lower()
    if explicit in ("light", "dark"):
        return explicit == "light"
    background = os.environ.get("COLORFGBG", "").rsplit(";", 1)[-1]
    return background in ("7", "15")


C = LIGHT if is_light() else DARK

THEME = Theme(name="springer", dark=C is DARK, primary=C["accent"], secondary=C["soft"], accent=C["accent"],
              warning=C["accent"], error=C["error"], success=C["success"], foreground=C["text"],
              background=C["background"], surface=C["surface"], panel=C["selected"])

RISK = {"L0": "dim", "L1": "system", "L2": "soft", "L3": "error"}
COLUMN = {"ready": "dim", "in_progress": "accent", "in_review": "soft", "blocked": "error", "done": "success"}


def paint(text, color=None, bold=False):
    style = " ".join(x for x in ("bold" if bold else "", C[color] if color else "") if x)
    return Text(str(text), style=style)


def join(*parts):
    """Assemble painted parts and plain strings into one Text."""
    return Text.assemble(*[p if isinstance(p, Text) else Text(str(p)) for p in parts])


def lines(rows):
    return Text("\n").join(rows)


def keys(*pairs):
    """A hint row: each key in amber, what it does in gray."""
    parts = []
    for index, (key, label) in enumerate(pairs):
        if index:
            parts.append("   ")
        parts += [paint(key, "accent"), paint(f" {label}", "dim")]
    return join(*parts)
