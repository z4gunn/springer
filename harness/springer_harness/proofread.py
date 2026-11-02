"""Spelling and grammar for what a person writes into the brief, checked before it is
written. LanguageTool runs on this machine, so no text leaves it. It downloads once on
first use and starts in the background, and until it is ready, or if Java is missing,
a dictionary check answers for spelling alone. Words a person adds are kept in
~/.springer/dictionary.txt and never flagged again."""

import re
import threading

from spellchecker import SpellChecker

WORD = re.compile(r"[A-Za-z][A-Za-z']*[A-Za-z]|[A-Za-z]")
# Not prose: a link, a path, a file name, code, or a word with a digit or an inner capital.
SKIP = re.compile(r"https?://\S+|\S*/\S*|`[^`]*`|\b\w+\.\w{1,4}\b|\b\w*\d\w*\b|\b[a-z]+[A-Z]\w*\b|\b[A-Z]{2,}\b")
MAX_SUGGESTIONS = 3
# Words a product brief uses that a general dictionary does not know.
PRODUCT_WORDS = """app apps backend frontend signup signups login logins logout onboarding offboarding checkout
dashboard dashboards webhook webhooks email emails inbox ui ux api apis url urls saas ios android admin admins
analytics workflow workflows timeline realtime macros macro calorie calories subscription subscriptions
username usernames passwordless dropdown dropdowns modal modals toggle toggles tooltip tooltips sidebar
homepage landing mockup mockups wireframe wireframes stripe vercel github repo repos csv pdf json
""".split()


class Proofreader:
    """check(texts) answers for several texts at once, keyed the way the caller keys its
    fields. Each issue carries an offset and a length into its own text."""

    def __init__(self, home_root, languagetool=False, language="en-US"):
        self.words_path = home_root / "dictionary.txt"
        self.spelling = SpellChecker()
        self.spelling.word_frequency.load_words(PRODUCT_WORDS + self.words())
        self.language = language
        self.tool = None
        self.state = "starting" if languagetool else "off"
        self._lock = threading.Lock()
        if languagetool:
            threading.Thread(target=self._start, name="languagetool", daemon=True).start()

    def _start(self):
        try:
            import language_tool_python

            tool = language_tool_python.LanguageTool(self.language, new_spellings=self.words() or None,
                                                     new_spellings_persist=False)
        except Exception:  # no Java, no network for the first download, or no package
            self.state = "unavailable"
            return
        self.tool, self.state = tool, "ready"

    def words(self):
        if not self.words_path.exists():
            return []
        return [w.strip() for w in self.words_path.read_text().splitlines() if w.strip()]

    def add_word(self, word):
        word = word.strip()
        if not word or word.lower() in {w.lower() for w in self.words()}:
            return
        with self.words_path.open("a") as f:
            f.write(word + "\n")
        self.spelling.word_frequency.load_words([word])

    def check(self, texts):
        engine = "languagetool" if self.state == "ready" else "spelling"
        issues = {}
        for key, text in texts.items():
            found = self._grammar(text) if engine == "languagetool" else self._spell(text)
            if found:
                issues[key] = found
        return {"engine": engine, "preparing": self.state == "starting", "issues": issues}

    def _grammar(self, text):
        known = {w.lower() for w in self.words()}
        with self._lock:  # one request at a time to the local server
            matches = self.tool.check(text)
        issues = []
        for m in matches:
            wrong = text[m.offset:m.offset + m.error_length]
            if wrong.lower() in known or _skipped(text, m.offset):
                continue
            issues.append({"offset": m.offset, "length": m.error_length, "text": wrong, "message": m.message,
                           "replacements": list(m.replacements[:MAX_SUGGESTIONS]),
                           "spelling": "MORFOLOGIK" in (m.rule_id or "") or "SPELL" in (m.rule_id or "")})
        return issues

    def _spell(self, text):
        issues = []
        for match in WORD.finditer(text):
            word = match.group()
            if len(word) < 3 or _skipped(text, match.start()) or _a_name(text, match.start(), word):
                continue
            if word.lower() not in self.spelling.unknown([word]):
                continue
            frequency = self.spelling.word_frequency
            candidates = sorted(self.spelling.candidates(word) or [], key=lambda w: (-frequency[w], w))
            candidates = [c for c in candidates if c != word.lower()]
            if word[0].isupper():
                candidates = [c.capitalize() for c in candidates]
            issues.append({"offset": match.start(), "length": len(word), "text": word,
                           "message": f"{word} may be misspelled.", "replacements": candidates[:MAX_SUGGESTIONS],
                           "spelling": True})
        return issues


def _a_name(text, offset, word):
    """A capitalized word inside a sentence is most likely a name, which a dictionary
    does not know. LanguageTool judges names itself, so this is the fallback's rule."""
    before = text[:offset].rstrip(" \t")
    return word[0].isupper() and bool(before) and before[-1] not in ".!?\n:"


def _skipped(text, offset):
    return any(m.start() <= offset < m.end() for m in SKIP.finditer(text))

