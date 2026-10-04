"""spgr-ingest-document/scripts/ingest_document.py: the deterministic
conversion step behind the content-sources rule. Both engines are optional,
so the script is exercised with fake binaries on PATH and with none."""

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

ing = load_script(REPO / ".claude" / "skills" / "spgr-ingest-document" / "scripts" / "ingest_document.py")

RICH = "# Title\\n\\nA paragraph long enough to count as real text, repeated to pass the density floor. " * 4
FAKE_MARKITDOWN_RICH = f"""#!/bin/sh
if [ "$1" = "--version" ]; then echo "markitdown 0.1.3"; exit 0; fi
printf '{RICH}\\n'
exit 0
"""
FAKE_MARKITDOWN_THIN = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "markitdown 0.1.3"; exit 0; fi
printf 'a b c\\n'
exit 0
"""
FAKE_DOCLING = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "docling 2.70.0"; exit 0; fi
# docling <file> --to md --output <dir>
src="$1"; shift
while [ $# -gt 0 ]; do case "$1" in --output) out="$2"; shift;; esac; shift; done
stem="${src##*/}"; stem="${stem%.*}"
printf '# From docling\\n\\n| a | b |\\n|---|---|\\n| 1 | 2 |\\n' > "$out/$stem.md"
exit 0
"""


def write_exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class IngestDocumentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.old_path = os.environ.get("PATH", "")
        self.old_home = os.environ.get("HOME", "")
        self.old_cwd = os.getcwd()
        os.environ["HOME"] = str(self.root / "home")
        (self.root / "home").mkdir()
        os.chdir(self.root)
        os.environ["PATH"] = str(self.bin)
        (self.root / "spec.pdf").write_bytes(b"%PDF-1.4 fake")
        (self.root / "brief.docx").write_bytes(b"PK fake docx")
        (self.root / "notes.md").write_text("# Notes\n\nhello\n")

    def tearDown(self):
        os.chdir(self.old_cwd)
        os.environ["PATH"] = self.old_path
        os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def run_script(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ing.main(["ingest_document.py", *args, "--out", "docs/inputs", "--json"])
        return rc, json.loads(buf.getvalue())

    def header(self, slug):
        text = (self.root / "docs" / "inputs" / f"{slug}.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        front, body = text[4:].split("\n---\n", 1)
        return dict(line.split(": ", 1) for line in front.splitlines()), body

    def test_no_engine_exits_two_for_a_binary_document(self):
        rc, report = self.run_script("spec.pdf")
        self.assertEqual(rc, 2)
        self.assertEqual(report["results"][0]["status"], "tool-missing")
        self.assertFalse((self.root / "docs" / "inputs" / "spec.md").exists())

    def test_markdown_is_copied_with_a_provenance_header_and_no_engine(self):
        rc, report = self.run_script("notes.md")
        self.assertEqual(rc, 0)
        self.assertEqual(report["results"][0]["status"], "copied")
        head, body = self.header("notes")
        self.assertEqual(head["source_file"], "notes.md")
        self.assertEqual(head["converter"], "copy")
        self.assertEqual(head["extraction_confidence"], "confirmed")
        self.assertEqual(len(head["source_sha256"]), 64)
        self.assertIn("# Notes", body)

    def test_office_document_converts_through_markitdown_as_confirmed(self):
        write_exec(self.bin / "markitdown", FAKE_MARKITDOWN_RICH)
        rc, report = self.run_script("brief.docx")
        self.assertEqual(rc, 0)
        self.assertEqual(report["results"][0]["status"], "converted")
        self.assertEqual(report["results"][0]["engine"], "markitdown")
        head, _ = self.header("brief")
        self.assertEqual(head["converter_version"], "markitdown 0.1.3")
        self.assertEqual(head["source_size_bytes"], str(len(b"PK fake docx")))
        self.assertEqual(head["extraction_confidence"], "confirmed")
        self.assertRegex(head["retrieved"], r"^\d{4}-\d{2}-\d{2}$")

    def test_thin_pdf_escalates_to_docling_when_present(self):
        write_exec(self.bin / "markitdown", FAKE_MARKITDOWN_THIN)
        write_exec(self.bin / "docling", FAKE_DOCLING)
        rc, report = self.run_script("spec.pdf")
        self.assertEqual(rc, 0)
        self.assertEqual(report["results"][0]["engine"], "docling")
        head, body = self.header("spec")
        self.assertEqual(head["converter"], "docling")
        self.assertEqual(head["extraction_confidence"], "confirmed")
        self.assertIn("| a | b |", body)

    def test_thin_pdf_without_docling_is_written_as_needs_human_input(self):
        write_exec(self.bin / "markitdown", FAKE_MARKITDOWN_THIN)
        rc, report = self.run_script("spec.pdf")
        self.assertEqual(rc, 0)
        self.assertEqual(report["results"][0]["status"], "needs-human-input")
        head, _ = self.header("spec")
        self.assertEqual(head["extraction_confidence"], "needs-human-input")

    def test_tables_flag_marks_a_rich_pdf_when_docling_is_absent(self):
        write_exec(self.bin / "markitdown", FAKE_MARKITDOWN_RICH)
        rc, report = self.run_script("spec.pdf", "--tables")
        self.assertEqual(rc, 0)
        self.assertEqual(report["results"][0]["status"], "needs-human-input")

    def test_collision_is_reported_and_force_replaces(self):
        write_exec(self.bin / "markitdown", FAKE_MARKITDOWN_RICH)
        self.run_script("brief.docx")
        (self.root / "brief.docx").write_bytes(b"PK a different docx")
        rc, report = self.run_script("brief.docx")
        self.assertEqual(rc, 1)
        self.assertEqual(report["results"][0]["status"], "collision")
        rc, report = self.run_script("brief.docx", "--force")
        self.assertEqual(rc, 0)
        self.assertEqual(report["results"][0]["status"], "converted")

    def test_unsupported_and_missing_files_fail_with_exit_one(self):
        (self.root / "image.png").write_bytes(b"\x89PNG")
        rc, report = self.run_script("image.png", "nope.docx", "notes.md")
        self.assertEqual(rc, 1)
        statuses = [r["status"] for r in report["results"]]
        self.assertEqual(statuses, ["failed", "failed", "copied"])

    def test_engine_is_found_in_local_bin_when_not_on_path(self):
        local = self.root / "home" / ".local" / "bin"
        local.mkdir(parents=True)
        write_exec(local / "markitdown", FAKE_MARKITDOWN_RICH)
        rc, report = self.run_script("brief.docx")
        self.assertEqual(rc, 0)
        self.assertEqual(report["engines"]["markitdown"], str(local / "markitdown"))


if __name__ == "__main__":
    unittest.main()
