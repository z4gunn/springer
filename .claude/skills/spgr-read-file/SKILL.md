---
name: spgr-read-file
description: Read a repository file as line-numbered text with binary, size, and missing-path handling. Use when an agent needs to read existing source, config, or artifact files before analyzing or editing them, or as the read side of the read-before-write contract.
---

# read-file

## Purpose

Give every agent one consistent read interface that returns accurate 1-indexed line numbers and handles the edge cases that cause silent failures: binary files, missing paths, oversized files, and out-of-repo traversal. Downstream edit tools reference the line numbers returned here, so numbering is load-bearing and must be exact.

## Inputs

| Field | Description |
|-------|-------------|
| `file_path` | Absolute or repo-relative path to read |
| `line_start` | Optional first line, 1-indexed, defaults to 1 |
| `line_end` | Optional last line, defaults to end of file |
| `encoding` | Optional, defaults to utf-8 |

## Outputs

| Artifact | Description |
|----------|-------------|
| `read_result` | Object: `file_path`, `file_exists`, `is_binary`, `line_count`, `file_size_bytes`, `line_start`, `line_end`, `contents` |

## Procedure

1. Resolve `file_path` and confirm it stays within the repository root. Refuse any path that traverses outside the repo and return an error.
2. If the file does not exist, return `file_exists: false` and suggest up to three alternative paths found by codebase search. Do not return empty content silently.
3. Detect binary by scanning the first 8KB for null bytes. If binary, return `is_binary: true` with a short message and no content.
4. Read the requested range. For a file over 500KB with no range given, return the first 200 lines and a truncation notice carrying the total line count. The caller must request a range for more.
5. Prefix each returned line with its 1-indexed number. Normalize line endings to LF in output and record the source style in metadata.

## Notes

- Treat reads as the read side of the read-before-write contract. `spgr-write-file` and the artifact-write skills refuse to operate on a file not read in the current session.
- Reading a file is a precondition for editing it, never a substitute for the agent's own analysis.
