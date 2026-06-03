---
name: spgr-create-release-tag
description: Create an annotated, optionally GPG-signed git tag in `vX.Y.Z` form at a release commit and push it to the remote, marking the exact source state a deployment is built from. Use when the DevOps Agent has a post-bump version, a release commit SHA, and a signed-off deployment runbook, and must tag the source before deployment begins, or when a downstream agent needs the permanent link between a deployed artifact and its source code.
---

# create-release-tag

## Purpose

Create one annotated git tag at the release commit, push it to the remote, and record the action in the decision log. The tag is the permanent link between a deployed artifact and the source it was built from, so "what code is in production?" resolves to a single `git show vX.Y.Z`. Annotated tags carry a message, tagger identity, and timestamp, all required for the audit trail. This skill writes a git ref and verification output, not an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `version` | Post-bump semantic version string, tagged as `vX.Y.Z` with the `v` prefix |
| `commit_sha` | SHA of the release commit the tag points at |
| `tag_message` | Release notes or changelog excerpt for the tag message: version, release date, one-line summary of key changes |
| `sign` | Whether to GPG-sign the tag, set true for security-sensitive projects |

## Outputs

| Artifact | Description |
|----------|-------------|
| Annotated git tag | `vX.Y.Z` tag at the release commit, GPG-signed when `sign` is true |
| Pushed remote ref | The tag pushed to the remote so CI and audit can resolve it |
| Decision log entry | A record via spgr-log-decision noting the tag, commit, and signing state |

## Procedure

1. Validate inputs before touching git. Confirm `version` parses as semantic version and the tag name will be `vX.Y.Z` with the `v` prefix. Confirm `commit_sha` resolves to a real commit in the repository. Confirm `tag_message` is non-empty. If any check fails, stop and call spgr-escalate with the missing or malformed field. Do not invent a version or message.
2. Confirm the tag does not already exist on the local repo or the remote. Run `git tag -l vX.Y.Z` and `git ls-remote --tags origin vX.Y.Z`. A release tag is immutable once pushed, so if the tag already exists, stop and call spgr-escalate. Never delete or move an existing release tag. To correct a bad release, the caller bumps to a new corrective version (for example `v1.4.1`) and re-invokes this skill.
3. Confirm the deployment runbook is signed off. Tag creation happens after runbook sign-off and before deployment begins, because the tag identifies what is being deployed. If sign-off is not present in the inputs, stop and call spgr-escalate.
4. Create the annotated tag at the commit. Use `git tag -a vX.Y.Z <commit_sha> -m "<tag_message>"`. When `sign` is true, use `git tag -s` instead of `-a` so the tag is GPG-signed and carries cryptographic proof the release was authorized by a known identity. Never create a lightweight tag.
5. Verify the tag locally before pushing. Run `git show vX.Y.Z` and confirm it points at `commit_sha`, carries the message, and is annotated. When signed, run `git tag -v vX.Y.Z` and confirm signature verification passes. If verification fails, delete the unpushed local tag, then stop and call spgr-escalate. A signing failure must not be pushed.
6. Push the single tag to the remote with `git push origin vX.Y.Z`. Push only this tag, not `--tags`, to avoid pushing unrelated local tags. If the push is rejected because the ref now exists on the remote, stop and call spgr-escalate rather than forcing.
7. Record the action with spgr-log-decision: the tag name, the target commit, the signing state, and the runbook sign-off reference. Tag the DevOps vertical for visibility with spgr-tag-vertical-agent when the calling agent is not the DevOps Agent.

## Notes

- Output type is a git ref and source operation, not an envelope artifact, so no spgr-write-artifact or spgr-validate-artifact call applies. There is no content schema for a git tag. Verification is the `git show` and `git tag -v` checks in steps 5 and 6, the equivalent of a CI check.
- Tag naming is always `vX.Y.Z` with the `v` prefix for consistency with tooling that expects it. This follows the DevOps semantic-versioning rule.
- Tags are immutable once pushed. The skill never deletes or moves a pushed release tag. Correction is a new corrective version, handled by re-invocation, not by retagging.
- GPG signing is required only in security-sensitive projects. When `sign` is true and the signing key is unavailable or verification fails, the skill escalates rather than falling back to an unsigned tag.
- Read input fields and the runbook sign-off via spgr-read-artifact or spgr-read-file as provided by the caller. Do not reach outside the supplied inputs to source a version or message.
