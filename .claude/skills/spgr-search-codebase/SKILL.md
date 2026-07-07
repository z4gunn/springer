---
name: spgr-search-codebase
description: Find symbols, patterns, or strings across the repository and return line-numbered, context-rich matches with a one-line interpretation of what the pattern means. Use when a QA, developer, or code-reviewer agent must locate where a symbol is defined or used, or assess the blast radius of a change before writing or reviewing code.
---

# search-codebase

## Purpose

Give a code-changing agent precise, line-numbered evidence of where a symbol is defined, where it is called, and what patterns already exist, so the agent does not duplicate logic, break callers silently, or reimplement something that is already present. This is a read-only navigation step that runs before any write. It returns structured match data to the calling agent rather than writing an artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `search_term` | Literal string, regex pattern, or symbol name to find |
| `file_glob` | Optional file pattern (for example `**/*.ts`, `src/api/**/*.py`) to scope the search |
| `language_filter` | Optional language identifier (`typescript`, `python`, `swift`, `kotlin`, and so on) |
| `context_lines` | Surrounding lines to include per match, default 3 |
| `case_sensitive` | Boolean, default false for symbol searches and true for string literals |

## Outputs

| Artifact | Description |
|----------|-------------|
| `match_list` | Each match as file path, line, column, and matched line content |
| `context_snippets` | Each match with `context_lines` of surrounding code |
| `match_count` | Count of unique matches and unique files matched |
| `search_summary` | One sentence interpreting what the pattern means in this codebase |
| `skipped_binaries` | Count of binary files skipped silently during the search |

## Procedure

1. Read `search_term`, `file_glob`, `language_filter`, `context_lines` (default 3), and `case_sensitive`. If `case_sensitive` is unset, default it to false for a symbol or identifier search and true for a string literal.

2. If `search_term` is presented as a regex, validate the regex syntax before running. On a parse error, fall back to a literal search of the same term and report to the calling agent that the regex was invalid and a literal search ran instead. Do not silently change the search semantics.

3. Construct the search as a ripgrep command following the template `rg --json -n -C {context_lines} {flags} '{search_term}' {path}`. Set `{flags}` from the inputs: `-i` when not case sensitive, `--glob '{file_glob}'` when a glob is given, `--type {language}` when a language filter maps to a ripgrep type. Scope `{path}` to the repository root or to the glob.

4. Rely on ripgrep default ignore behavior so files in `.gitignore`, `.dockerignore`, and `node_modules/` are not searched. Do not add flags that override these ignores. Binary files are skipped silently, so capture the skipped count for `skipped_binaries`.

5. For a symbol search (a function, class, or method name), run both a literal search and a regex search that covers common naming variants of the same symbol (camelCase, snake_case, PascalCase) so a rename or convention difference does not hide a real usage. Merge the results and dedupe by file and line.

6. Parse ripgrep `--json` stdout into the output fields. Populate `match_list`, attach `context_lines` of surrounding code to each as `context_snippets`, and set `match_count` to unique matches and unique files matched.

7. When `match_count` exceeds 50, do not return every line. Group matches by directory, return a directory-level count summary, and offer to drill into a named directory on the next call.

8. When `match_count` is zero, propose three alternative search terms reasoned from the original term (a naming-variant form, a substring, and a related concept), then re-run automatically with the highest-confidence alternative and label that result as an automatic fallback so the agent knows the term changed.

9. Write `search_summary` as one sentence that interprets the result for the caller, for example what the symbol appears to be and where its definition and primary call sites sit. Return all output fields to the calling agent.

## Notes

- This skill produces a read-only search result returned to the calling agent, not an envelope artifact with a registered schema. There is no `spgr-write-artifact` call and no schema validation step.
- Reading matched file contents in full, when an agent needs more than the context window, is done through spgr-read-file rather than re-running the search with a wider context.
- The output schema shape is `{ term, file_glob, matches: [{file, line, col, text, context}], match_count, files_matched, search_summary, skipped_binaries }`. If a future increment must persist a search result for handoff, it would be written through spgr-write-artifact with a registered schema added at that time.
- Keep the search scoped. Pass the narrowest `file_glob` or `language_filter` the calling task allows, so the result stays relevant and the directory-summary path at over 50 matches is rarely needed.
