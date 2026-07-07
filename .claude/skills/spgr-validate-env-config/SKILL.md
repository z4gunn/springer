---
name: spgr-validate-env-config
description: Generate a startup environment-configuration validation module that checks required variables, validates formats, reports all errors together, and exits non-zero on failure, plus a non-production /health/config endpoint. Use when the DevOps or backend developer agent needs the application to fail fast at startup on missing or invalid configuration.
---

# validate-env-config

## Purpose

Produce a startup configuration validation module so the application refuses to start when configuration is missing or invalid, with a clear message naming the variable, what is wrong, and what a valid value looks like. A misconfigured deployment that fails at startup is preferable to one that starts, serves some traffic, and fails midway through a critical operation when it first reaches the misconfigured service. The module is source code, validated test-first and by CI, not an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `env_inventory` | Environment variable inventory parsed from `.env.example`, read through spgr-read-file |
| `validation_rules` | Per-variable rules: required vs optional, and format (URL, email, integer, enum, minimum length) |

## Outputs

| Artifact | Description |
|----------|-------------|
| `env validation module` | Source code that on startup checks presence, validates formats, aggregates all errors, and exits non-zero on any failure. Written via spgr-write-file |
| `config health endpoint` | A `/health/config` route, enabled in non-production environments only, that reports which variables are set and which are missing, never their values. Written via spgr-write-file |
| `validation tests` | Failing tests written before the module, covering missing required, invalid format, and all-clear cases. Written via spgr-write-file |

## Procedure

1. Read `.env.example` through spgr-read-file to derive the variable inventory. Confirm each variable has a validation rule. If a variable has no stated rule, escalate through spgr-escalate rather than guessing required-vs-optional or its format.
2. Choose the validation library that matches the project stack: Zod for TypeScript, pydantic for Python, envconfig for Go, dotenv-safe for Node.js. Do not hand-roll validation. Edge cases in manual parsing are common.
3. Write the failing tests first through spgr-write-file: one case asserting startup fails and lists a missing required variable, one asserting an invalid-format value is rejected with a specific message, and one asserting a fully valid environment passes. Run them through spgr-run-tests and confirm they fail before writing the module.
4. Implement the validation module so it runs at startup, not lazily. Check every required variable is present. Validate formats where a rule applies. Aggregate all failures and report them together, not one at a time, so a developer fixes the whole set in one pass.
5. Write each error to name the variable, state what was wrong, and show what a valid value looks like, for example "WEBHOOK_SECRET must be at least 32 characters for adequate entropy". Never include the value of a sensitive variable (password, API key, secret) in any validation or log output.
6. Exit with a non-zero code on any validation failure so a process supervisor or CI gate treats startup as failed.
7. Add the `/health/config` endpoint, guarded so it serves only in non-production environments. Report each variable as set or missing by name. Never emit a value.
8. Run spgr-run-tests again to confirm the suite now passes, then run spgr-format-code and spgr-lint-code to reach a clean tree before commit.
9. If a rule is internally contradictory (a variable marked both required and optional) or a format rule cannot apply to the declared type, stop and raise spgr-escalate with the precise conflict rather than resolving it by assumption.

## Notes

- The output is source code, verified by spgr-run-tests and CI, not by an envelope schema.
- Keep one logical change per commit through spgr-git-commit: the validation module and its tests are one change, the health endpoint is a separate change.
- Build only the rules the inventory and `validation_rules` specify. Do not add validation for variables that are not in the inventory.
