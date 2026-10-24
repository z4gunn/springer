---
name: spgr-install-runtime
description: Install or update the Springer runtime in a project from this plugin's copy. Creates a new instance in an empty directory, adopts an existing repository, or brings an instance up to this plugin's version. Use when a person asks to set up, adopt, or update Springer.
disable-model-invocation: true
---

# install-runtime

## Purpose

Springer runs from a copy of its runtime inside each project, because its agents, skills, schemas, and harness scripts are cited by repository-relative path. The plugin carries that runtime but does not run it from the plugin cache. This skill installs it where it belongs, with the same scripts a Springer checkout uses, and nothing else from the plugin loads into a session.

## Inputs

| Field | Description |
|-------|-------------|
| `target` | The project directory, default the current working directory |
| `profile` | `brochure`, `small`, `saas`, `mobile`, or `api`, asked when the target has no manifest |

## Procedure

1. Find the plugin root: it is three directories above this skill's base directory, the one that holds `scripts/update-project.py`. Confirm the file exists there before running anything, and stop with the path you looked at if it does not.
2. Read the target's state and pick the one mode it allows:
   - `.claude/springer-manifest.json` exists: update. Run `python3 <root>/scripts/update-project.py status <target>`, show the person the summary, ask through the question tool whether to apply it, and on yes run `update <target>`.
   - The target is empty or does not exist: new instance. Ask for the profile with the four questions from the run-profiles rule (an app store, money or tenants, a user interface, otherwise `api`), then run `bash <root>/scripts/new-project.sh <target> <profile>`.
   - Anything else: adopt. Ask for the profile the same way, then run `python3 <root>/scripts/update-project.py adopt <target> --profile <profile>`. A refusal lists the runtime paths that already hold different content. Show the list and ask whether to move them aside or rerun with `--force`. Never pass `--force` without that answer.
3. Report what the script printed, the default lane (`build` for a new instance, `polish` for an adopted repository), and the next step: start a run with the spgr-run-harness skill in the project.

## Notes

- Never edit the plugin cache. A change to the runtime is made in a Springer checkout and reaches projects through an update.
- The scripts refuse to touch a project while a harness holds a live run lock. Report the refusal and the run that holds it.
