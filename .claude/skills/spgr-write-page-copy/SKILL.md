---
name: spgr-write-page-copy
description: Produce a page-copy artifact for a brochure page or a saas marketing page, with headline, subheadline, call to action, sourced proof, section copy in the users' own vocabulary, and a [NEED] row for every missing fact, linted against the copy standards. Use after the PRD is confirmed and before the build unit for any public page.
---

# write-page-copy

## Purpose

Springer's discovery skills record the exact words users reach for, and nothing downstream has consumed them: the build unit writes the page's copy itself, mid-implementation, from whatever a model produces for a brief of that shape. This skill gives the page a copy owner before any markup exists. It turns the confirmed PRD, the personas, and the discovery vocabulary into one typed page-copy artifact the frontend developer uses verbatim, holds it to `.claude/references/copy-standards.md`, and surfaces every fact the inputs do not hold as a `[NEED: ...]` row instead of inventing it. On the brochure profile the artifact is written in the requirements unit so the content-sources table and the intake questions are complete before the first gate.

## Inputs

| Field | Description |
|-------|-------------|
| `prd_artifact_path` | The confirmed PRD, read for the value proposition, the audience, the content-sources table, and `open_questions`. |
| `persona_artifact_paths` | The personas, read for the reader's goals and objections. |
| `icp_artifact_path` | The ICP, which fixes the one audience the copy addresses. |
| `vocabulary_artifact_paths` | The pain-point taxonomy, the forum analysis, or any mining artifact carrying `user_vocabulary` and `verbatim_examples` with source URLs. |
| `section_list` | The page's sections in order, from the IA artifact or the screen spec. Defaults to the page structure in the reference. |
| `brand_constraints` | Optional. Tone words, product naming rules, claims the human has approved or forbidden. |
| `page_type` | `landing`, `pricing`, `docs-landing`, `comparison`, or `other`. Selects the structure variant in the reference. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `page-copy` | Envelope artifact. Per section: `section_id`, `headline`, `subheadline`, `cta` (label and destination), `body` as ordered paragraphs or list items, `proof` items each with `source_ref`, and `needs` as `[NEED: ...]` rows. Top level: `page_type`, `audience` from the ICP, `vocabulary_used` (the user phrases carried into copy with their source URLs), `lint_result`, and `sources`. |
| `lint_result` | The output of `scripts/copy_lint.py` on the final copy, clean, recorded in the artifact. |

## Procedure

1. Read every input with spgr-read-artifact. Stop and raise spgr-escalate if the PRD is not confirmed, if no ICP names the audience, or if no vocabulary artifact exists on a profile where discovery ran. On brochure, where the human's spec stands in for discovery, read the spec under `docs/inputs/` with spgr-read-file and treat its phrasing as the vocabulary source.

2. Read `.claude/references/copy-standards.md` in full. It is the bar and the fix list.

3. Fix the audience and the one outcome. Write one line naming who the page speaks to, from the ICP, and one line naming the outcome they want, in a phrase lifted from `user_vocabulary` or a verbatim quote. Every section below is written to that reader and that outcome. Record both with spgr-log-decision.

4. Build the vocabulary list. From the mining artifacts collect the recurring user phrases and the strongest verbatim quotes, each with its source URL. These are the words the headline, the problem section, and the objections use. A phrase the product team uses and users do not is replaced by the users' phrase.

5. Build the proof inventory. List every fact the copy may state: each row of the PRD content-sources table, each sourced figure or customer in the brief, each quote with a URL. Nothing outside this inventory enters the copy as a fact. This is the fact rule in the reference.

6. Write each section in `section_list` order, applying the page structure for `page_type`. For every section produce the headline, the subheadline where the section has one, the call to action where the section has one, the body, and the proof items with `source_ref`. Where a sentence needs a fact the inventory lacks, write `[NEED: <what and where>]` in its place and add the row to `needs`. One primary call to action per page, repeated verbatim at the close.

7. Run the swap test on each section as the reference describes. Rewrite any section that would stand unchanged on a competitor's page, drawing the specificity from the vocabulary list and the proof inventory, never from invention.

8. Lint. Write the draft copy to a scratch file and run:

   ```bash
   python3 .claude/skills/spgr-write-page-copy/scripts/copy_lint.py <draft.md>
   ```

   Fix every finding and run again until the exit code is 0. Pass `--allow <phrase>` only for a phrase the brand constraints require, and record each allowance with spgr-log-decision. Then read the Severity section of the reference and check the patterns the lint cannot see: abstract subjects, vague connections, synonym cycling across sections, re-explaining.

9. Write the artifact with spgr-write-artifact, carrying the sections, `vocabulary_used`, `sources`, the clean `lint_result`, and a confidence map that marks a section `proposed` when it carries any `[NEED]` row and `confirmed` otherwise. Run spgr-validate-artifact inline.

10. Hand the `needs` rows upstream. On brochure and small, each `[NEED]` row is a needs-human-input row in the PRD content-sources table and an intake question with a recommended default, per the PM agent's intake sweep. Return the artifact path and the count of open needs to the calling agent.

## Notes

- Output type is a page-copy envelope artifact. No content schema is registered for it yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until one is registered.
- The copy in this artifact is used verbatim by the frontend developer. A wording change during the build is a fold-in to this artifact, not an edit in markup, so the lint and the fact rule stay in force.
- The fact rule is absolute. A `[NEED]` marker is the correct output for a missing fact, and an invented name, number, date, or quote is a defect at any severity.
- Interface strings (button labels, field labels, rendered error text) are owned by the screen specs and design-quality.md. This skill writes the page's prose and the call-to-action labels it names.
- The lint script is deterministic and runs with no model. Dispatch it at the deterministic tier. The writing is judgment and runs at the calling agent's tier.
- This skill has no Phase 1 vault spec. It was authored to the Springer build standards as a net-new capability.
