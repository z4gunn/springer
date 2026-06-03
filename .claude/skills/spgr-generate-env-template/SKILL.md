---
name: spgr-generate-env-template
description: Create and maintain the project .env.example file as source code, the complete documented template of every environment variable the application requires, each with a one-line description, a safe example value, a required-or-optional annotation, and the environments it applies to, grouped under comment headers, and completeness-checked by scanning the codebase for env access patterns. Use when the DevOps developer agent stands up a project's configuration contract, or when any commit adds, removes, or renames an environment variable and the template must be updated in the same change.
---

# generate-env-template

## Purpose

Maintain `.env.example`, the contract between the application and its configuration. Every environment variable the code reads must appear here with a description, a safe example value, and a required-or-optional annotation, so a new contributor can configure the project without reading source. A variable used in code but absent from the template causes a confusing runtime failure on first run. A variable in the template but never read in code is dead configuration that misleads. This skill keeps the template complete in both directions by scanning the codebase and reconciling it against the template.

## Inputs

| Field | Description |
|-------|-------------|
| `codebase` | The application source tree. Scanned for environment-variable access patterns. Read with spgr-read-file. |
| `existing-env-template` | The current `.env.example` if one exists, so the update is a reconciliation rather than a rewrite. Read with spgr-read-file. |
| `variable-metadata` | Per-variable categorization: required vs optional, which environments it applies to (development only, all environments, production only), and a safe example value (test API key, localhost URL, boolean default, placeholder secret). |

## Outputs

| Artifact | Description |
|----------|-------------|
| `.env.example` (source code) | One entry per environment variable the application uses, each carrying the variable name, a one-line description of what it configures, a safe example value, a required-or-optional annotation, and the environments it applies to. Related variables are grouped under comment headers (for example `# Database`, `# Authentication`, `# External Services`). Written with spgr-write-file. |

## Procedure

1. Read the existing `.env.example` with spgr-read-file if one exists. Treat its current entries, ordering, and group headers as the baseline to reconcile against, not a blank slate to overwrite.

2. Scan the codebase for environment-variable access patterns with spgr-read-file and Grep: `process.env.` for Node, `os.environ.get(` and `os.environ[` for Python, `ENV[` for Ruby, `getenv(` and `System.getenv(` for C and Java, and the equivalent for the project's stack. Collect the full set of variable names the code reads.

3. Reconcile the scanned set against the template entries. Compute two differences. Variables read in code but missing from the template are completeness gaps. Variables present in the template but never read in code are dead configuration.

4. For each variable read in code but missing from the template, add an entry with its description, safe example value, required-or-optional annotation, and applicable environments from `variable-metadata`. If `variable-metadata` does not supply a safe example value or the required-or-optional classification for a newly found variable, stop and raise spgr-escalate with the precise list of variables that lack metadata. Do not invent a value, and never write a real secret into the file.

5. For each variable in the template but not read in code, do not silently delete it. Flag it as suspected dead configuration and raise spgr-escalate with the list, since the variable may be read through indirection the scan cannot see or may be slated for imminent use. Removal is a human-confirmed decision.

6. Group related variables under comment headers and order entries so the file reads top to bottom by concern. Confirm every example value is safe: test credentials, localhost URLs, placeholder secrets, or boolean defaults only. Never a production credential.

7. Write the reconciled `.env.example` to disk with spgr-write-file, honoring the read-before-write contract.

8. Record the reconciliation result with spgr-log-decision: variables added, variables flagged as dead, and any metadata gap that triggered an escalation, so the reasoning is traceable in the same commit.

## Notes

- The output is source code, verified by the completeness scan in this procedure and by CI rather than by an envelope schema. There is no registered artifact schema for `.env.example`.
- `.env.example` is committed to the repository and holds example values only. Real secrets live in `.env` (local, gitignored) or in a secrets manager for staging and production. This skill never writes a real secret.
- Update `.env.example` in the same commit as any change that adds, removes, or renames an environment variable. A stale template is a primary onboarding-friction source. Keep one logical change per commit and the file format clean before commit.
- Every variable in the template must be read somewhere in the application code, and every variable read in code must appear in the template. The scan in step 2 and the reconciliation in step 3 enforce both directions.
