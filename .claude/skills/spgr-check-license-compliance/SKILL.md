---
name: spgr-check-license-compliance
description: Produce a license-compliance report that audits every direct and transitive dependency license against the project's distribution model and allowed-license list, classifying each flagged dependency by category (copyleft, commercial restriction, unknown, disallowed), giving a per-dependency compliant, requires-review, or disallowed verdict with remediation, and returning a PASS or GATE verdict that fails the build on any disallowed license category. Use when the Security Agent must confirm a release or architecture review carries no incompatible dependency license, or when a CI dependency-introduction gate needs the current license posture before a GPL, SSPL, or unlicensed package reaches a commercial product.
---

# check-license-compliance

## Purpose

Audit the licenses of all direct and transitive dependencies to find license obligations, incompatibilities, and commercial-use restrictions before legal review rather than during it. Dependency licenses carry legal obligations that decide whether a product can be distributed, sold, or run as a commercial service. A GPL dependency linked into a commercial closed-source product creates an obligation to open-source that product. An SSPL dependency restricts use in a commercial SaaS offering. An unlicensed package means all rights reserved, so using it without permission is a legal risk. This skill reads the dependency tree, classifies each license against the project's distribution model and allowed list, and returns a report whose gate verdict blocks the build on any disallowed license.

## Inputs

| Field | Description |
|-------|-------------|
| `lock_files` | Package lock file(s) for each ecosystem in the project, read with spgr-read-file. |
| `distribution_model` | One of commercial closed-source, open-source, or internal use. Decides which categories are disallowed. |
| `allowed_licenses` | Project-configurable allowed-license list in SPDX identifiers (defaults: MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC). |
| `prior_report` | The previous license-compliance report, if any, read with spgr-read-artifact to diff posture and version. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `license-compliance` | Envelope artifact written with spgr-write-artifact. Holds the full dependency license inventory, flagged dependencies grouped by category, a per-flagged-dependency verdict (compliant, requires-review, disallowed), remediation per disallowed or restricted entry, and one overall PASS or GATE verdict. |

## Procedure

1. Read each lock file with spgr-read-file. Run the license-identification tool for each ecosystem present: `license-checker` for Node.js, `pip-licenses` for Python, `go-licenses` for Go. Request SPDX identifiers so each license is named unambiguously. Cover direct and transitive dependencies.

2. Build the full inventory: every dependency, its resolved version, its SPDX identifier, and whether it is direct or transitive.

3. Classify each license. Mark as allowed any identifier on `allowed_licenses`. Flag the rest into one category: copyleft (GPL, LGPL, AGPL), commercial restriction (SSPL, BSL), unknown (unlicensed packages, custom or non-SPDX text), or disallowed (a category barred by the distribution model).

4. Resolve copyleft in a transitive dependency before assigning a verdict. Determine whether the package is linked into the distributed binary or used only in build tooling. Build-time-only use of GPL tooling does not trigger the copyleft obligation, so record that finding and set the verdict to compliant. Linked GPL or AGPL in a closed-source distribution sets the verdict to disallowed.

5. Apply the distribution model. For a SaaS project, flag SSPL specifically: an SSPL dependency requires the entire serving stack to be released under SSPL, so set its verdict to disallowed for a commercial SaaS model. For a commercial closed-source model, treat linked copyleft as disallowed.

6. Set every unknown license to requires-review. No license means all rights reserved, so it cannot ship without manual legal confirmation. Tag the Compliance Agent with spgr-tag-vertical-agent for each requires-review entry that needs a legal judgment this skill cannot make.

7. Write remediation per disallowed or restricted dependency: a permissively licensed replacement, removal, or a path to a commercial license grant.

8. Set the overall verdict. Return GATE if any dependency carries a disallowed verdict. Return PASS only when no disallowed verdict remains and every requires-review entry has a recorded legal sign-off. Record the verdict and its basis with spgr-log-decision.

9. Validate the artifact with spgr-validate-artifact before writing it. On a GATE verdict, raise spgr-escalate with the disallowed list, the categories, and remediation so the build stops at the gate. When the verdict needs human legal judgment, route it with spgr-notify-human. Version the report with spgr-version-artifact against `prior_report`.

## Notes

- Output type is an envelope artifact (a findings report). The `license-compliance` type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it.
- This skill is the CI license gate. A new dependency introduction that adds a disallowed license category returns GATE and fails CI immediately. Wire the GATE verdict as a blocking exit in the pipeline.
- The skill does not give legal advice. A requires-review verdict is an escalation to the Compliance Agent and the human, not a clearance.
- Confidence signals: an SPDX-identified license verdict is confirmed, a copyleft-linkage determination that could not be verified from the dependency graph is proposed, and an unknown or custom license is needs-human-input.
