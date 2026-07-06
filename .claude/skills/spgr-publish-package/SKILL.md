---
name: spgr-publish-package
description: Publish a versioned build artifact to its target registry (npm, PyPI, container registry, app store, or internal store), idempotently, with a publication record appended to the release artifact. Use when the DevOps Agent has a built artifact and a confirmed release tag, or when a dry-run must verify publish credentials before a real release.
---

# publish-package

## Purpose

Publish is the one-way door that makes a release available to consumers. Each target type (npm or PyPI for libraries and SDKs, a container registry for services, TestFlight or the app stores for mobile, an internal store for private artifacts) has its own authentication, validation, and rollback story. Encode the correct publish procedure for the target, make the operation idempotent so re-running the same version succeeds cleanly or fails with a clear already-published signal rather than silently overwriting, and record the publication on the release artifact so the release history stays traceable.

## Inputs

| Field | Description |
|-------|-------------|
| `build-artifact` | The package, container image, or binary to publish |
| `target-registry` | The registry type and endpoint (npm, PyPI, container registry, app store, internal store) |
| `publish-credentials` | Auth injected from the CI secrets store, never read from pipeline config |
| `version` | The version string, verified against the release tag |
| `distribution-tier` | Internal beta versus public release |
| `dry-run` | When set, validate structure and credentials without publishing |

## Outputs

| Artifact | Description |
|----------|-------------|
| Published artifact | The build artifact live in the target registry at `version` |
| Publication record | Registry URL, version, and publish timestamp appended to the release artifact via spgr-write-artifact |

## Procedure

1. Read the release tag and the build artifact with spgr-read-file. Confirm `version` matches the release tag exactly. If they differ, stop and escalate with spgr-escalate.
2. Confirm publish credentials resolve from the CI secrets store. Never accept credentials from a pipeline configuration file, and never print them to build logs. If credentials are missing or unresolved, escalate with spgr-escalate.
3. For an app store target, confirm the App Store Compliance Agent pre-submission checklist has passed before submitting. Tag the vertical with spgr-tag-vertical-agent if the checklist verdict is missing, and do not submit until it passes.
4. Run a dry-run first. Validate the package structure and that credentials authenticate against the target, without publishing. When the input `dry-run` flag is set, stop here and report the dry-run result.
5. Check idempotency. Query the registry for `version`. If it already exists, do not overwrite. Report an already-published signal and exit cleanly without error only when the published artifact matches. Otherwise escalate the conflict with spgr-escalate.
6. Publish to the target. For a container registry, push the immutable `version` tag first, then move `latest` to point at the new version only after the version push succeeds. For npm or PyPI, publish at `version` against the resolved registry endpoint.
7. Verify the publish landed by reading the version back from the registry. If verification fails, escalate with spgr-escalate rather than reporting success.
8. Append the publication record (registry URL, version, publish timestamp, distribution tier) to the release artifact. Write it with spgr-write-artifact and validate inline with spgr-validate-artifact. Bump the artifact version with spgr-version-artifact and record the publish with spgr-log-decision.
9. Notify the human of a public-release publish with spgr-notify-human.

## Notes

- Output is a SOURCE or CONFIG action (artifact pushed to a registry) plus an envelope publication-record appended to the release artifact. The registry push is verified by reading the version back. The appended record is checked by spgr-validate-artifact, which applies envelope-only validation until a content schema is registered for the release artifact.
- Public-registry publish is a one-way door. A version cannot be unpublished without consequence (npm deprecation, PyPI yank, broken consumer builds). Verify the artifact before publishing.
- Container `version` tags are immutable. Only `latest` moves, and only after the version push succeeds.
- Credentials come from the CI secrets store. No literal secret appears in any pipeline or IaC file or in build logs.
- Follow semantic versioning. The published `version` must match the release tag.
