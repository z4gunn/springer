---
name: spgr-write-file
description: Create or overwrite a repository file safely, with read-before-write enforcement, parent-directory creation, backup, and post-write checksum verification. Use when an agent needs to write source, config, or artifact files to disk, since the artifact-write skills call this as their write side.
---

# write-file

## Purpose

Give every agent one safe write interface so file production does not cause missing directories, blind overwrites of unread files, or partial writes on crash. This skill does not generate content. The caller assembles the full content string, and this skill writes it atomically and confirms the result.

## Inputs

| Field | Description |
|-------|-------------|
| `file_path` | Absolute or repo-relative path to write |
| `content` | Full file content as a string |
| `mode` | `create` (fail if exists), `overwrite` (replace unconditionally), or `safe` (fail if not read this session). Defaults to `safe` |
| `create_parents` | Create missing parent directories. Defaults to true |
| `encoding` | Defaults to utf-8 |

## Outputs

| Artifact | Description |
|----------|-------------|
| `write_result` | Object: `write_confirmed`, `file_path`, `bytes_written`, `created_dirs`, `backup_path`, `checksum` |

## Procedure

1. Resolve `file_path` and confirm it stays within the repository root. Refuse writes outside the repo boundary.
2. In `safe` mode, confirm the file was read this session with `spgr-read-file`. If it was not, escalate with `spgr-escalate` rather than writing blindly.
3. In `create` mode, fail with a clear error if the file already exists. Do not silently overwrite.
4. When overwriting an existing file, copy it to a `.bak` in a temp directory and record the path in `backup_path`.
5. Write to a temp file in the same directory, then move it to the target path so a crash cannot leave a partial write. Create parent directories first when `create_parents` is true and record them in `created_dirs`.
6. Verify the write by re-reading the first and last five lines and comparing a checksum. Return `write_confirmed` with the checksum.

## Notes

- Write LF line endings by default. Respect an explicit `create_line_ending` of CRLF only for Windows-targeted config files.
- When several agents may write the same shared file, take a file lock around the write to prevent a race.
