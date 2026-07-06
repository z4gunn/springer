---
name: spgr-lint-code
description: Run the project linter on modified files, auto-fix safe violations in place, and produce a lint report listing violations that need manual resolution. Use when a developer agent has changed files and must reach zero lint errors before commit, or when the Code Reviewer agent needs the lint posture of a PR branch.
---

# lint-code

## Purpose

Linting enforces correctness rules that formatting does not catch, such as unused variables, unreachable code, deprecated API usage, and security anti-patterns. Zero lint errors is a Definition-of-Done requirement and CI blocks merge on any lint failure. Run the project's configured linter on the changed files, apply only the auto-fixes that cannot change program behavior, and hand back a report of every violation a human still has to resolve.

## Inputs

| Field | Description |
|-------|-------------|
| `changed_files` | The files modified in the PR or branch, the lint target |
| `lint_config` | The project's linter config (ESLint, Ruff, golangci-lint, Clippy, SwiftLint, ktlint or Detekt) including any security ruleset |

## Outputs

| Artifact | Description |
|----------|-------------|
| Auto-fixed source files | The changed files rewritten with safe, behavior-preserving fixes applied, written via spgr-write-file |
| Lint report | Per-violation list (file, line, rule, message, suggested fix) for the issues that need manual resolution, plus a summary of issues auto-fixed and issues remaining |

## Procedure

1. Identify the linter from the language and the present config (JavaScript or TypeScript uses ESLint, Python uses Ruff or Flake8 with pylint, Go uses golangci-lint, Rust uses Clippy, Swift uses SwiftLint, Kotlin uses Detekt or ktlint). Confirm the project config is loaded so rule severity matches the repo, not the linter defaults. For TypeScript or JavaScript, the required ESLint config and rule set (the gts base plus the Springer overrides) are defined in `.claude/references/typescript-standards.md`. Confirm that config is in effect, not bare linter defaults.
2. Confirm the security ruleset is active for the language (eslint-plugin-security, bandit, gosec or the stack equivalent) so common vulnerability patterns are caught in the same pass.
3. Run the linter in auto-fix mode against `changed_files` only. Apply a fix in place only when it is deterministic and cannot change runtime behavior, such as removing an unused import or correcting a simple style violation.
4. Collect the violations the auto-fixer left behind. Flag for manual resolution any fix that could change behavior, that suppresses a rule, or that requires understanding the author's intent.
5. Do not add a rule suppression. A suppression such as `// eslint-disable-next-line` without a documented rationale in an adjacent code comment is a violation to flag, not a fix to apply.
6. Write the lint report and the summary counts (issues auto-fixed, issues requiring manual resolution).
7. If the report lists any remaining error-severity violation, the changed set is not Definition-of-Done clean. Return the report so the calling agent resolves each violation before commit. Re-run from step 3 after a fix.

## Notes

- The auto-fixed files are source code, verified by spgr-run-tests and CI rather than by an envelope schema. Run the test suite after auto-fix to confirm no fix changed behavior.
- The lint report is an artifact type not yet in the registered schema list. Write it via spgr-write-artifact with its registered schema added in a later increment, and validate inline with spgr-validate-artifact once that schema exists.
- Read the target files with spgr-read-file before fixing, honoring the read-before-write contract.
- Zero lint errors is the Definition-of-Done gate. A branch with any remaining lint error does not merge.
- When a security rule fires on a pattern the author cannot resolve within the approved architecture, raise it through spgr-escalate rather than suppressing the rule.
