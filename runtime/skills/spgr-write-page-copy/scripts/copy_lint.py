#!/usr/bin/env python3
"""Lint generated copy against the mechanical subset of copy-standards.md.

Deterministic, no model. A model asked for product copy produces the same
defaults every time (a contrast reveal, a banned phrase, bold labels on every
bullet), and the same patterns leak into READMEs, release notes, and listing
copy. This script catches the subset a regular expression can see so the
agent spends its judgment on the rest: the banned phrases, em and en dashes,
exclamation points, "not X but Y" and "not just X" constructions, bold labels
on consecutive bullets, sentences over 25 words, three consecutive list items
with the same opening word, and a heading echoed by the sentence after it.

Usage:
    copy_lint.py <path>... [--json] [--allow <phrase>]...
    copy_lint.py - < draft.md

Inputs are Markdown, plain text, HTML, or JSON. HTML is reduced to its text
and JSON to its string values before scanning. A directory is walked for
.md, .txt, .html, and .json files.

Exit 0 when clean, 1 when there are findings, 2 when a path could not be
read. The copy-standards reference owns the pattern list. This file owns the
regular expressions that approximate it.
"""

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

BANNED = [
    "say goodbye to", "say hello to", "unlock the power of", "unleash",
    "reimagined", "redefined", "take your", "to the next level", "supercharge",
    "everything you need", "all in one place", "effortless", "effortlessly",
    "in just a few clicks", "in seconds", "join thousands", "trusted by leaders",
    "loved by teams", "game-changer", "game-changing", "game changer",
    "revolutionary", "cutting-edge", "next-generation", "experts agree",
    "studies show", "it is well known", "seamless", "seamlessly", "frictionless",
    "robust", "powerful", "elegant", "intuitive", "best-in-class", "world-class",
    "leverage", "leverages", "utilize", "utilizes", "facilitate", "facilitates",
    "empower", "empowers", "whether you're a", "whether you are a",
    "from startups to enterprises", "in today's fast-paced", "now more than ever",
    "dive in", "dive deep", "delve", "it's not just", "it is not just",
    "not only", "unlock", "elevate", "streamline", "harness",
]

SENTENCE_WORD_CAP = 25
EXTENSIONS = {".md", ".txt", ".html", ".htm", ".json"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in ("p", "li", "h1", "h2", "h3", "h4", "br", "div", "td", "th"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(text):
    p = _TextExtractor()
    p.feed(text)
    return "".join(p.parts)


def json_to_text(text):
    try:
        obj = json.loads(text)
    except ValueError:
        return text
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(obj)
    return "\n".join(out)


def to_text(text, suffix):
    if suffix in (".html", ".htm"):
        return html_to_text(text)
    if suffix == ".json":
        return json_to_text(text)
    return text


def strip_markup(line):
    """Drop list markers, heading hashes, and inline code so patterns see prose."""
    line = re.sub(r"`[^`]*`", "", line)
    line = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line)
    line = re.sub(r"^\s*#{1,6}\s+", "", line)
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
    return line


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def first_words(text, n=1):
    words = re.findall(r"[A-Za-z']+", text.lower())
    return tuple(words[:n])


def lint_text(text, allow=(), name="<stdin>"):
    findings = []
    allowed = {a.lower() for a in allow}
    lines = text.splitlines()
    heading = None
    bold_run = 0
    opener_run = []
    in_fence = False

    def add(line_no, pattern, match):
        findings.append({"file": name, "line": line_no, "pattern": pattern,
                         "match": match.strip()[:120]})

    for i, raw in enumerate(lines, 1):
        if re.match(r"^\s*```", raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        is_heading = bool(re.match(r"^\s*#{1,6}\s+", raw))
        is_bullet = bool(re.match(r"^\s*(?:[-*+]|\d+\.)\s+", raw))
        line = strip_markup(raw)
        low = line.lower()
        if not line.strip():
            if not is_bullet:
                bold_run = 0
                opener_run = []
            continue

        spans = []
        for phrase in sorted(BANNED, key=len, reverse=True):
            if phrase in allowed:
                continue
            for m in re.finditer(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", low):
                if any(a <= m.start() and m.end() <= b for a, b in spans):
                    continue
                spans.append((m.start(), m.end()))
                add(i, "banned-phrase", line[m.start():m.end()])

        for ch, pid in (("—", "em-dash"), ("–", "en-dash")):
            if ch in raw:
                add(i, pid, raw)

        if "!" in line and not re.search(r"!\[", raw):
            add(i, "exclamation", line)

        m = re.search(r"\b(?:it'?s|this is|that'?s|we'?re|they'?re|you'?re)?\s*not (?:just |only |merely |simply )?(?:a |an |the )?[^.,;]{1,40}?[,.]?\s*(?:but|it'?s|it is)\b", low)
        if m and re.search(r"\bnot\b", low):
            add(i, "contrast-reveal", line[m.start():m.end()])

        if is_bullet and re.match(r"^\s*(?:[-*+]|\d+\.)\s+(\*\*|__)[^*_]+(\*\*|__)", raw):
            bold_run += 1
            if bold_run == 2:
                add(i, "bold-decoration", raw)
        elif not is_bullet:
            bold_run = 0

        if is_bullet:
            opener_run.append((i, first_words(line)))
            if len(opener_run) >= 3:
                last = opener_run[-3:]
                if last[0][1] and last[0][1] == last[1][1] == last[2][1]:
                    add(i, "parallel-openers", " / ".join(lines[j - 1].strip() for j, _ in last))
                    opener_run = []
        else:
            opener_run = []

        if is_heading:
            heading = first_words(line, 3)
            if re.match(r"^(?:[A-Z][a-z]+\s+){2,}[A-Z][a-z]+$", line.strip()):
                add(i, "decorative-heading", line)
        elif heading is not None:
            if heading and first_words(line, len(heading)) == heading:
                add(i, "heading-echo", line)
            heading = None

        if not is_heading:
            for s in split_sentences(line):
                if len(re.findall(r"[A-Za-z0-9']+", s)) > SENTENCE_WORD_CAP:
                    add(i, "long-sentence", s)

    return findings


def read_input(path):
    if path == "-":
        return [("<stdin>", sys.stdin.read(), ".md")]
    p = Path(path)
    if p.is_dir():
        files = sorted(f for f in p.rglob("*") if f.suffix.lower() in EXTENSIONS)
    else:
        files = [p]
    out = []
    for f in files:
        try:
            out.append((str(f), f.read_text(encoding="utf-8"), f.suffix.lower()))
        except (OSError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"{f}: {exc}")
    return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow", action="append", default=[])
    args = ap.parse_args(argv[1:])

    findings = []
    try:
        for path in args.paths:
            for name, text, suffix in read_input(path):
                findings.extend(lint_text(to_text(text, suffix), args.allow, name))
    except RuntimeError as exc:
        print(f"copy_lint: could not read {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    else:
        for f in findings:
            print(f"{f['file']}:{f['line']}  {f['pattern']:18} {f['match']}")
        print(f"copy_lint: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
