"""scripts/eval-skills.py: the checker is a pure function of a stream-json
transcript, so every assertion type is tested here without a model."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

ev = load_script(REPO / "scripts" / "eval-skills.py")


def tool(name, inp, parent=None):
    return json.dumps({"type": "assistant", "parent_tool_use_id": parent,
                       "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})


def result(text):
    return json.dumps({"type": "result", "subtype": "success", "result": text})


TRANSCRIPT = [
    json.dumps({"type": "system", "subtype": "init"}),
    tool("Agent", {"subagent_type": "spgr-agent-backend-developer", "prompt": "..."}),
    tool("Read", {"file_path": "/w/src/textutil.py"}, parent="toolu_1"),
    tool("Write", {"file_path": "/w/tests/test_slug.py", "content": "..."}, parent="toolu_1"),
    tool("Edit", {"file_path": "/w/src/textutil.py", "old_string": "a", "new_string": "b"}, parent="toolu_1"),
    tool("Bash", {"command": "python3 .claude/skills/spgr-run-harness/scripts/receipt.py run u --name unit -- x"},
         parent="toolu_1"),
    "not json",
    result("DONE\n2 commits"),
]


class CheckerTest(unittest.TestCase):
    def check(self, *expect, lines=TRANSCRIPT):
        return ev.check({"id": "t", "prompt": "p", "expect": list(expect)}, lines)

    def test_parse_scopes_and_final(self):
        calls, final = ev.parse_transcript(TRANSCRIPT)
        self.assertEqual([c["scope"] for c in calls], ["main"] + ["subagent"] * 4)
        self.assertEqual(final, "DONE\n2 commits")

    def test_called_never_before_final(self):
        sub = {"scope": "subagent"}
        r = self.check(
            {"type": "called", "match": dict(sub, tool="^Bash$", input="receipt\\.py run")},
            {"type": "never", "match": {"tool": "^Write$", "input": "lint\\.json"}},
            {"type": "before", "first": dict(sub, tool="Write|Edit", input="tests/"),
             "then": dict(sub, tool="Write|Edit", input="src/")},
            {"type": "final", "pattern": "\\bDONE\\b"})
        self.assertTrue(r["passed"], r)
        self.assertEqual(r["calls"], 5)

    def test_failures_are_reported(self):
        r = self.check(
            {"id": "order", "type": "before", "first": {"tool": "Edit", "input": "src/"},
             "then": {"tool": "Write", "input": "tests/"}},
            {"id": "missing", "type": "before", "first": {"tool": "Write", "input": "tests/"},
             "then": {"tool": "Write", "input": "nope"}},
            {"id": "never", "type": "never", "match": {"tool": "^Read$"}},
            {"id": "scope", "type": "called", "match": {"tool": "^Agent$", "scope": "subagent"}},
            {"id": "final", "type": "final", "pattern": "BLOCKED"})
        self.assertFalse(r["passed"])
        self.assertEqual([a["passed"] for a in r["assertions"]], [False] * 5)
        self.assertIn("both must occur", r["assertions"][1]["detail"])

    def test_path_command_and_or_matchers(self):
        report = tool("Write", {"file_path": "/w/u/result.md", "content": "edited src/textutil.py"}, parent="t")
        heredoc = tool("Bash", {"command": "cat > src/textutil.py <<'EOF'\nx\nEOF"}, parent="t")
        lines = [report, heredoc]
        src = {"or": [{"tool": "Write|Edit", "path": "src/textutil\\.py$"},
                      {"tool": "^Bash$", "command": ">\\s*src/textutil\\.py"}]}
        self.assertEqual(ev.first_index(ev.parse_transcript(lines)[0], src), 1)
        self.assertIsNone(ev.first_index(ev.parse_transcript([report])[0],
                                         {"tool": "Write", "path": "src/textutil\\.py$"}))
        self.assertEqual(ev.first_index(ev.parse_transcript([report])[0],
                                        {"tool": "Write", "input": "src/textutil"}), 0)

    def test_any_of(self):
        r = self.check({"type": "any_of", "of": [{"type": "final", "pattern": "zero-run"},
                                                 {"type": "called", "match": {"tool": "^Bash$"}}]})
        self.assertTrue(r["passed"])
        r = self.check({"type": "any_of", "of": [{"type": "final", "pattern": "zero-run"}]})
        self.assertFalse(r["passed"])

    def test_every_shipped_scenario_loads_and_uses_known_assertions(self):
        known = {"called", "never", "before", "final", "any_of"}
        scenarios = sorted((REPO / "evals").glob("*.json"))
        self.assertGreaterEqual(len(scenarios), 5)
        for path in scenarios:
            s = ev.load_scenario(path)
            self.assertEqual(s["id"], path.stem)
            stack = list(s["expect"])
            while stack:
                a = stack.pop()
                self.assertIn(a["type"], known, path.name)
                stack.extend(a.get("of", []))
            self.check(*s["expect"])

    def test_cli_check_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp) / "s.json"
            scenario.write_text(json.dumps({"id": "s", "prompt": "p",
                                            "expect": [{"type": "final", "pattern": "DONE"}]}))
            transcript = Path(tmp) / "t.jsonl"
            transcript.write_text("\n".join(TRANSCRIPT))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ev.main(["eval-skills.py", "check", str(scenario), str(transcript)]), 0)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ev.main(["eval-skills.py"]), 2)
            self.assertEqual(ev.main(["eval-skills.py", "check", "only-one"]), 2)
            self.assertEqual(ev.main(["eval-skills.py", "run", "--bogus"]), 2)


if __name__ == "__main__":
    unittest.main()
