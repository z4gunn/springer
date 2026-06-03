---
name: spgr-generate-sbom
description: Generate a Software Bill of Materials (SBOM) in CycloneDX or SPDX format from a release's lock and manifest files, recording every direct and transitive component with version, package URL, SHA-256 hash, and license, then attach it to the release artifact and upload it to continuous vulnerability monitoring. Use when the Security Agent produces the supply-chain inventory for a release so a future CVE can be answered by lookup rather than manual audit, or when the DevOps Agent attaches an SBOM to a release artifact as a pipeline step.
---

# generate-sbom

## Purpose

Produce a machine-readable inventory of every software component in a release so a newly published CVE can be answered by lookup rather than by manual audit. The SBOM describes the exact dependency set of one release at release time, not the current development state. It is generated with a pinned tool version for reproducible output, attached to the release artifact, and uploaded to continuous vulnerability monitoring so new CVEs against listed components raise automated alerts.

## Inputs

| Field | Description |
|-------|-------------|
| `lock_files` | Package lock file(s) and manifest files for the release commit, covering every language ecosystem in the build. |
| `build_metadata` | Build artifact metadata identifying the release version and the source state the SBOM describes. |
| `output_format` | SBOM format, `cyclonedx` or `spdx`. Default to `cyclonedx` when unspecified. |
| `tool_version` | Pinned SBOM generator version (for example `syft`, `cyclonedx-bom`, `cdxgen`) so output is reproducible across runs. |

## Outputs

| Artifact | Description |
|----------|-------------|
| SBOM document | The generated SBOM file written via spgr-write-file, listing component name, version, package URL (pURL), SHA-256 hash, and license for every direct and transitive dependency, plus the dependency relationship graph and SBOM metadata (creation timestamp, generator tool and version, format version). |

## Procedure

1. Read the release lock files, manifests, and build metadata for the release commit using spgr-read-file. Confirm the inputs describe the release state and not uncommitted development state.
2. Select the format. Default to CycloneDX because it has wider supply-chain tooling support (Grype, Syft, Dependency-Track). Use SPDX only when the consumer requires it.
3. Run the pinned SBOM generator against the lock files and build artifact. Pin the tool version so a re-run on the same source produces identical output.
4. Verify the generated SBOM lists every direct and transitive component, and that each component carries a name, version, pURL, SHA-256 hash, and license. If any component is missing a hash or a license, record it and escalate before treating the SBOM as complete.
5. Write the SBOM file with spgr-write-file and verify generation in CI. The SBOM is attached to the release artifact and retained alongside it for as long as the release is supported, since it is needed for post-release CVE response.
6. Upload the SBOM to Dependency-Track or the equivalent continuous vulnerability monitor so new CVEs against listed components raise automated alerts.
7. Record the generation as a decision with spgr-log-decision, then validate the run record with spgr-validate-artifact.

## Notes

- Output type is a generated SBOM source file written via spgr-write-file and verified in CI, not an envelope artifact. The accompanying run record validates through spgr-validate-artifact, which falls back to envelope-only validation (header, confidence map, decision log, version) because no content schema is registered for SBOM output yet.
- Escalate via spgr-escalate when lock or manifest files are missing for an ecosystem present in the build, when the generator cannot resolve a transitive dependency, or when a component lacks a hash or license, since an incomplete SBOM gives false supply-chain assurance.
- Tag the Compliance Agent with spgr-tag-vertical-agent when component license data is needed for license-compliance review, and notify the release owner with spgr-notify-human when the SBOM is attached and uploaded.
- The SBOM is generated at release time and pinned to the release source. Do not regenerate it against a later development state, because it must continue to describe the dependency set of the release it is attached to.
