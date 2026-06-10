---
name: spgr-audit-doc-coverage
description: Produce a documentation coverage audit report that measures API reference, docstring, developer-guide, README, and changelog coverage against the shipped code and the release scope, lists every gap, and returns a COMPLETE or GAPS verdict that blocks release on undocumented public API changes and major user-facing features. Use when the Documentation Agent, or the QA or code-reviewer agent, must confirm a release is documented before it ships, or when a CI sweep needs the current documentation posture.
---

# audit-doc-coverage

## Purpose

Documentation coverage erodes on every release that ships code without the matching docs. New endpoints reach external developers with no API reference entry, new features land with no guide, and new configuration appears with no README update. Make those gaps visible as a release-blocking criterion rather than an afterthought. Compare the shipped code and the release scope against the existing documentation, list every gap by type, track docstring coverage as a metric over time, and return a verdict that blocks the release when a public API change or a major user-facing feature is undocumented.

## Inputs

| Field | Description |
|-------|-------------|
| `api_spec` | The OpenAPI spec for the release, the source of truth for which endpoints exist. Read so API reference coverage is measured against every defined operation. |
| `codebase` | The repository, scanned for public exports and their docstrings to compute docstring coverage. |
| `changelog` | The release changelog, compared against the release scope to find changes that are not recorded. |
| `release_scope` | The user-story or backlog set in the release, used to find shipped features that lack a guide and to decide what is a major user-facing feature. |
| `doc_inventory` | The existing documentation tree: API reference, developer guides, README, and changelog, the baseline this audit measures against. |
| `docstring_baseline` | The prior docstring coverage percentage, used to flag any drop below the established floor as a deliberate-decision gap. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `doc-coverage-report` | API coverage (endpoints with no docs, endpoints with incomplete docs), docstring coverage percentage with the list of undocumented public exports, guide coverage (release features with no guide), README freshness (stale versions, commands, or config, plus the quickstart result), changelog completeness (release changes not recorded), and the COMPLETE or GAPS verdict. Written via spgr-write-artifact. |

## Procedure

1. Read the api spec, the changelog, the documentation inventory, and the relevant code with spgr-read-file and the api spec via spgr-read-artifact. If the api spec, the release scope, or the documentation inventory is missing, stop and raise spgr-escalate naming what is absent, because coverage cannot be measured against an unknown baseline.
2. Measure API coverage. For every operation in the api spec, confirm a reference entry exists. Record each endpoint with no documentation, and each endpoint whose entry is incomplete, meaning a missing request or response example or a missing documented error code.
3. Measure docstring coverage from language tooling. Scan public exports, compute the percentage that carry a docstring, and list every undocumented public function. Compare the result to the docstring baseline and flag any drop below the floor as a gap that needs a deliberate decision rather than a silent regression.
4. Measure guide coverage. For each feature in the release scope, confirm a developer or user guide covers it. List every shipped feature with no guide and mark which of those are major user-facing features.
5. Check README freshness, focused on the quickstart. Confirm the quickstart commands, version references, and configuration match the current release. Run the quickstart from a clean environment. A quickstart that does not work from clean is a blocking gap.
6. Check changelog completeness. Compare the changelog against the release scope and the commit history. List every release change that is not reflected in the changelog.
7. Set the verdict. Return GAPS, blocking, when any public API change is undocumented, when a major user-facing feature has no guide, or when the quickstart fails from clean. Return GAPS, non-blocking, for lower-severity gaps such as a docstring dip on internal exports. Return COMPLETE only when no blocking gap remains. Record the verdict and any judgment call, such as what counts as a major feature, with spgr-log-decision.
8. Write the doc-coverage report with spgr-write-artifact and validate it inline with spgr-validate-artifact.
9. On a blocking verdict, raise spgr-escalate to the release gate with the precise gap list, and tag the Documentation Agent via spgr-tag-vertical-agent so the gaps are assigned rather than discovered at ship time.

## Notes

- Documentation gaps for public API changes are release-blocking. A new endpoint shipped without documentation is an unusable feature for external developers.
- Docstring coverage is a metric over time, not a one-time pass. A project that starts at sixty percent does not drop below that without a recorded decision, so always compare against the docstring baseline and emit the trend into the report summary.
- The README freshness check centers on the quickstart, because a quickstart that fails from a clean environment blocks every new developer regardless of the rest of the docs.
- This skill audits and reports only. It does not write the missing docs. API reference generation, docstring generation, and guide authoring belong to the dedicated documentation skills.
- Output type is an envelope artifact written via spgr-write-artifact. The doc-coverage-report type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Run this audit from CI on every release candidate so coverage is measured automatically: API coverage from api spec analysis, docstring coverage from language tooling, and changelog completeness from commit analysis.
