---
name: spgr-run-harness
description: Route a request to start, resume, or advance a Springer run to the harness daemon, which drives every run. Use when a person asks to run the team, build the product, or continue a run. It never drives the loop or writes run state from this session.
---

# run-harness

## Purpose

The harness daemon drives every run and is the one writer of its state, so this session must not. This skill tells the person where the run lives and leaves the run alone. Its policy is in `.claude/references/pdca-harness.md` and its durable state in `.claude/references/state-model.md`.

## Procedure

1. Read `runs/<run-id>/.lock` when the person named a run. A `session_id` starting with `daemon:` means the daemon holds it.
2. Tell the person to run `springer` in a terminal. It starts the daemon when none is running and opens the TUI, where the run, its gates, and its controls live. Say whether the daemon holds the named run.
3. Stop. Do not claim the run, dispatch an agent, or write anything under `runs/`.

## Notes

- Do not run `scripts/claim-run.py`, `scripts/rebuild-projection.py`, or any other script that writes run state, even to help. A second writer is the defect the run lock exists to prevent.
- The scripts and assets beside this file stay for what the daemon and its sessions call: `scripts/receipt.py` for gating commands and `assets/dispatch-preamble.md` for the unit contract.
