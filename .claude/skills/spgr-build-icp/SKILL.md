---
name: spgr-build-icp
description: Produce an icp artifact that names the one customer type to acquire first, with attributes, buying signals, willingness-to-pay, exclusion criteria, and a prioritization rationale. Use when the Discovery Agent has personas, competitive analysis, and market sizing and must settle who the product is built for first.
---

# build-icp

## Purpose

Translate a persona set into an Ideal Customer Profile, the sharper claim about which customer type to acquire first and which will generate durable revenue. A persona describes who might use the product. The ICP adds the attributes that predict conversion and retention, and the exclusion criteria that rule out customer types that will not convert. This skill is analytical synthesis over prior Phase 1 outputs, so it writes no code and tags no scanner. Its job is to select one primary ICP and defend that selection.

## Inputs

| Field | Description |
|-------|-------------|
| `persona_set` | Output from `spgr-build-persona`, read via spgr-read-artifact. One or more persona documents |
| `competitive_matrix` | Output from competitive analysis. Competitor positioning and gaps |
| `market_context` | TAM and SAM estimates, geography, and relevant market conditions |
| `business_model` | How the product makes money: subscription, usage-based, freemium, marketplace |
| `constraints` | Known exclusions: regulatory, technical, or operational limits that rule out customer types |

## Outputs

| Artifact | Description |
|----------|-------------|
| `icp` | Envelope artifact carrying the ICP document, prioritization rationale, exclusion criteria, and buying signals, written via spgr-write-artifact |

## Procedure

1. Read each input with spgr-read-artifact for prior artifacts and spgr-read-file for any loose source. Confirm a persona set, a competitive matrix, and market context are all present.
2. If any of the three required inputs is missing, empty, or self-contradictory, stop and raise spgr-escalate with the precise list of what is absent. Do not infer a persona or invent market numbers to fill the gap.
3. Classify the ICP as `B2B`, `B2C`, or `B2B2C` from the business model and persona set.
4. Score each candidate persona against four dimensions: problem-solution fit, willingness to pay, underservice by existing solutions (from the competitive matrix), and reachability. Select the one persona that maximizes the combination as the primary ICP.
5. Record the attributes that match the ICP type. For B2B, capture firmographics: company size range, industry vertical, tech stack indicators, team structure, budget authority structure, and typical sales cycle length. For B2C, capture demographics and behavioral attributes: usage frequency, platform, price sensitivity tier, and the trigger event that initiates product search. Set the unused attribute block to null.
6. Make the ICP more specific than its source persona. Narrow a persona like "power users who hate the incumbent's pricing" to a measurable profile such as "power users at or above usage tier X, in geography Y, paying Z for the incumbent, with renewal in 90 days."
7. Enumerate `buying_signals` as observable behaviors or events that indicate a high-fit prospect before that prospect self-identifies. These are the bridge to a future GTM strategy.
8. Record `exclusion_criteria` with a rationale per excluded customer type. Treat exclusions as load-bearing as inclusions, since they keep engineering time off edge cases that will never convert.
9. Capture `willingness_to_pay` as a range and a pricing model tied to the business model.
10. Write a `prioritization_rationale` that states why this ICP was selected over the other candidate personas, grounded in the four-dimension scoring.
11. Limit the artifact to one primary ICP for MVP. A second ICP may appear only as a labeled Phase 2 target and must not dilute initial scope decisions. Set every field's confidence to confirmed, proposed, or needs-human-input.
12. Write the artifact with spgr-write-artifact and run inline spgr-validate-artifact. Set the version with spgr-version-artifact and log the selection with spgr-log-decision.

## Notes

- Output type is an envelope artifact (`icp`). The `icp` content type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Content fields per the spec: `icp_id`, `product_context`, `icp_type`, `primary_persona_ref`, `firmographics` or null, `demographics` or null, `behavioral_attributes`, `buying_signals`, `willingness_to_pay`, `exclusion_criteria`, `prioritization_rationale`.
- This skill runs in Phase 1 discovery. Inputs are prior skill outputs and no web access or new mining is required here. Any factual claim carried forward keeps the source citation from its originating artifact.
- The PM Agent consumes this artifact as a secondary reader to anchor a story's target user. Do not duplicate persona detail. Reference the persona by `primary_persona_ref`.
