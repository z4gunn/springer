---
name: spgr-format-code
description: Run the project's configured code formatter on every file touched in a change, apply the results in place, and wire a pre-commit hook so staged files are formatted before each commit. Use when the backend, frontend, mobile, or DevOps developer agent has edited or created source files and needs them formatted to the committed config before lint, test, or commit, or when a repo has no formatter hook yet and one must be installed.
---

# format-code

## Purpose

Apply the project's committed formatter to all files a change touches, so the formatter is the single source of style truth and reviewers read logic diffs rather than whitespace churn. This skill does not invent style. It runs the formatter that the repo already pins and commits the formatted result. It also installs the pre-commit hook that keeps staged files formatted on every future commit, so formatting never reaches CI as a failure. The output is formatted source code and a hook config, not an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `touched_files` | The set of files modified in the current branch or PR, new and existing. Default to every file in the change, not only new files. |
| `formatter_config` | The repo's committed formatter config, for example `.prettierrc`, `pyproject.toml`, `.rustfmt.toml`, `.swift-format`, or `.editorconfig`, including its pinned formatter version. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Formatted source files | The touched files rewritten in place to match the committed formatter config. |
| Pre-commit hook config | A hook entry that runs the formatter on staged files before each commit, written when the repo has no such hook. |

## Procedure

1. Read the touched files and the formatter config with spgr-read-file. Detect the formatter from the config and language: Prettier for JavaScript and TypeScript, Black or Ruff format for Python, gofmt or goimports for Go, rustfmt for Rust, swift-format for Swift, ktlint for Kotlin.
2. Confirm the formatter binary is the pinned version recorded in the config. A version mismatch produces diff churn unrelated to the change, so stop on mismatch rather than reformatting against the wrong version.
3. Run the formatter against the full touched-file set, new and existing files alike. Existing code that the change touches gets corrected too.
4. Write each changed file back with spgr-write-file, which enforces read-before-write and verifies the post-write checksum.
5. If a repo lacks a pre-commit hook for the formatter, add one that runs the formatter on staged files, and record the choice with spgr-log-decision.
6. Treat the formatter output as authoritative. Do not hand-edit the result to override style. If the output is genuinely wrong, the fix is in the config, not the file.
7. Validation and escalation. Run the formatter once more in check-only mode and confirm it reports no remaining changes, which is the same gate CI runs. If the formatter binary or config is missing, the pinned version does not match, or the formatter errors on a file, raise spgr-escalate with the file, the formatter, and the expected version rather than committing partly formatted or wrongly versioned output.

## Notes

- The output is formatted source code and a hook config, verified by spgr-run-tests and the CI format check rather than by an envelope schema.
- The formatter runs in CI and blocks merge on any violation. A clean check-only pass locally means a clean pass in CI, because the config and pinned version are the same.
- The formatter config is committed and version-pinned so a formatter upgrade does not churn diffs. Do not bump the pinned version inside a feature change.
- Run format clean before commit, as one logical change per commit. Formatting is part of that single change, not a separate follow-up commit.
- Editor format-on-save is a contributor convenience, not the enforcement point. The pre-commit hook and CI check are the gates. Recommend editor integration in contributor docs owned by the repo, not in this skill.
