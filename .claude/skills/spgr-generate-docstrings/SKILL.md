---
name: spgr-generate-docstrings
description: Write inline docstrings for public APIs, exported functions, classes, and complex logic, documenting the caller-facing contract in the language's native convention, with a CI gate that fails on undocumented exported symbols. Use when the Documentation, developer, QA, or code-reviewer agent needs docstrings added in the same commit as the code.
---

# generate-docstrings

## Purpose

A docstring documents the contract a caller depends on, not the implementation a maintainer reads. Write docstrings that add information the code does not already express: parameter constraints that types do not enforce, the conditions under which each error is raised, side effects, ordering requirements, thread safety, and when a caller should prefer an alternative. Skip any docstring that only restates the signature in prose. The output is source code edited in place plus a CI gate, not an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `target_symbols` | The public API functions, exported functions, and classes to document, plus any complex internal logic flagged for documentation |
| `error_conditions` | The errors or exceptions each target can raise and the condition that triggers each |
| `side_effects` | State mutation, I/O, ordering requirements, thread-safety constraints, and other behavior not visible in the signature |
| `parameter_constraints` | Constraints not expressed by the type, for example must be a positive integer, must not be null, must be sorted |
| `language_convention` | The docstring convention for the file's language: JSDoc, TSDoc, Python docstring, Swift doc comment, or Go doc comment |

## Outputs

| Artifact | Description |
|----------|-------------|
| Edited source files | Each target symbol carries a docstring in its language's native convention, written in place into the file that defines the symbol |
| Doc-coverage CI gate | A check that scans exported symbols and fails the documentation quality gate when one lacks a docstring |

## Procedure

1. Read each target file with spgr-read-file before editing it, so docstrings are written against the current signature and body.
2. For each target symbol, decide whether a docstring adds information. If the only available content restates the signature (for example a docstring saying "Gets a user by ID" on `getUserById(id: string)`), skip it. Document a symbol when it has a non-obvious contract, an unenforced parameter constraint, a raised error, or a side effect.
3. Write each docstring in the file's language convention with a one-sentence description of what the function does rather than how, each parameter with its name, type, description, and any unenforced constraint, the return type and description, each raised error with its triggering condition, and the non-obvious contracts (side effects, ordering, thread safety, when to prefer an alternative).
4. Write the edited files with spgr-write-file. Edit only the symbols in scope and the docstring text. Do not change executable code, since docstrings ship in the same commit as the code they describe and must match the current implementation.
5. Stand up or update the doc-coverage gate: a CI check that enumerates exported symbols and fails when one has no docstring. Confirm it passes locally with spgr-run-tests before commit.
6. Escalate with spgr-escalate when a target's contract cannot be determined from the inputs or the code, for example an error path with no documented trigger, an ambiguous parameter constraint, or a side effect that is not evident. Return the precise list of symbols and the missing contract detail rather than inventing a contract.

## Notes

- The output is source code (docstrings in their source files plus the CI gate) verified by spgr-run-tests and CI, not by an envelope schema.
- The doc-coverage gate produces a doc-coverage report. When that report is emitted as a stored artifact, write it via spgr-write-artifact with its registered schema added in a later increment.
- A docstring that contradicts the current implementation is an active source of bugs. Update docstrings in the same commit as the code they document and never as a separate later pass.
- Document only symbols that add caller-facing information (YAGNI). Do not document every internal symbol to satisfy a count.
