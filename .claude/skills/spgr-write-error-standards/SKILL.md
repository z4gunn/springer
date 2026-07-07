---
name: spgr-write-error-standards
description: Produce an error-standards artifact that fixes how errors are caught, classified, logged, and surfaced, with an error taxonomy, response shapes, and a silent-failure prohibition. Use when the Resilience Agent sets project-wide error handling before services are built, or when an agent needs the agreed error-response shape to implement against.
---

# write-error-standards

## Purpose

Error handling is one of the most inconsistently built parts of a system. Without a standard, errors get caught at random levels, logged with different structure, surfaced to callers in different shapes, and sometimes swallowed. Produce the Resilience vertical's error-standards artifact so error handling is consistent across every service and every developer. This skill writes one envelope artifact. It does not implement error handling in any service, and it does not edit another agent's artifact. Where a horizontal agent owns the affected section (for example the API spec's error-response shape), route the recommendation through a consultation rather than editing that artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `service-topology` | Service list and tech stack. Error mechanisms differ by language and framework, so the standards are written against the actual stack. |
| `error-response-shape` | The external error response shape from the API design standards, if registered. |
| `logging-schema` | The logging schema artifact, for the structure of the error log entry. |
| `security-requirements` | What information must not appear in external error responses. |

Read each input with `spgr-read-artifact` (registered types) or `spgr-read-file` (source and config). If the tech stack, security exposure rules, or logging schema are missing or contradictory, stop and raise `spgr-escalate` with the precise list of what is missing rather than assuming a default.

## Outputs

| Artifact | Description |
|----------|-------------|
| `error-standards` | Envelope artifact carrying the error classification taxonomy, catch-point rules, per-class log standards, external and internal response shapes, panic and fatal handling, the silent-failure prohibition, and the static-analysis rule that enforces it. |

Write with `spgr-write-artifact` and validate inline with `spgr-validate-artifact`. Version with `spgr-version-artifact` on every revision and record consequential choices with `spgr-log-decision`.

## Procedure

1. Read every input artifact. Confirm the tech stack, the registered error-response shape, the logging schema, and the security exposure rules are present and consistent. Escalate via `spgr-escalate` if any required input is missing or two inputs conflict (for example a logging schema field that the security rules forbid in an external response).

2. Define the error classification taxonomy. Cover four classes at minimum: Transient (retriable), Client (4xx, not retriable), Server (5xx, internal), External (third-party service failure). State the retriable property and the owning layer for each class.

3. Set the catch-point rules. Errors are caught at the narrowest possible scope, not at the top level alone. State that errors propagate with added context at each layer rather than being discarded. An error of "user service failed" wrapping "database connection refused" wrapping "ECONNREFUSED" is more useful than "user service failed" alone, so require wrapping that preserves the original.

4. Set the log standards per class. Define which fields appear in the error log entry, keyed to the logging schema. 5xx errors carry a stack trace and log at ERROR and are alert-worthy. 4xx errors are expected behavior, carry no stack trace, and log at WARN or INFO, never ERROR.

5. Set the response standards. The external shape carries a machine-readable code and a human-readable message only. It must never include a stack trace, a file path, an internal variable name, or a database error message, since these leak implementation detail that aids an attacker. The internal shape carries full context for debugging.

6. Define panic and fatal handling. State how unrecoverable errors are handled, including the choice between graceful shutdown and restart, for the project's process model.

7. Write the silent-failure prohibition. An error must not be swallowed without logging. An empty catch block, and a catch block that only logs without re-throwing or returning, are banned. Define the static-analysis rule that flags both patterns so the prohibition is enforced in CI rather than by review alone, and name where it runs.

8. Write the artifact with `spgr-write-artifact` and run `spgr-validate-artifact` inline. If validation fails, correct the artifact and re-validate before returning.

9. Where the standards constrain a section another agent owns (the API error-response shape, the logging schema fields, a security exposure rule), register the recommendation through `spgr-tag-vertical-agent` as a consultation. Do not edit the other agent's artifact directly.

## Notes

- Output type is an envelope artifact (`error-standards`). Its content schema is registered in a later increment, so `spgr-validate-artifact` applies envelope-only validation for now (header, confidence map, decision log, version).
- Operate in the Resilience vertical's three modes. As consultant when a horizontal agent asks for the standards, as auditor on a scheduled sweep against built services, and as gate whose sign-off marks the standards confirmed.
- The static-analysis rule for empty and log-only catch blocks is part of the artifact's content, not a code change made by this skill. A developer or DevOps agent wires it into the linter and CI.
- Carry each section's confidence as confirmed, proposed, or needs-human-input in the artifact's confidence map. A standard that depends on a missing security exposure rule is needs-human-input, not a guess.
