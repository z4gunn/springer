---
name: spgr-go-no-go
description: Synthesize all discovery findings into a single build recommendation (go, no-go, or conditional-go) with evidence-cited rationale, top risks, and dissenting evidence, then route it to a mandatory human checkpoint. Use when the Discovery Agent has completed discovery and must decide whether the product is worth building before planning begins.
---

# go-no-go

## Purpose

Force the body of discovery research into one honest build recommendation: is this product worth building, and why. This is the most consequential gate in the pipeline, the point where research hours convert to engineering months. A false go on weak evidence is expensive. A clear no-go is valuable because it prevents building the wrong thing. The recommendation is never acted on autonomously. A human approves before planning begins.

## Inputs

| Field | Description |
|-------|-------------|
| `problem_statement` | The validated problem, grounded in cited user-research evidence |
| `icp_document` | Output from spgr-build-icp, the defined ideal customer profile |
| `competitive_matrix` | Output from spgr-competitive-analysis |
| `pain_point_taxonomy` | Output from spgr-synthesize-painpoints |
| `feasibility_notes` | Technical and operational feasibility signals, can the team build this |
| `market_size` | Output from spgr-market-sizing, the TAM and SAM for the business model |

## Outputs

| Artifact | Description |
|----------|-------------|
| `recommendation` | `go`, `no-go`, or `conditional-go` |
| `rationale` | Narrative supporting the recommendation, 3 to 5 paragraphs, evidence-cited |
| `supporting_evidence` | Key data points that most strongly support the recommendation, each with a source reference |
| `key_risks` | Top 3 to 5 risks that could invalidate the recommendation, each with likelihood, impact, and a mitigation note |
| `differentiation_case` | The specific claim the product can credibly make and defend against the competitive landscape |
| `conditions` | For `conditional-go` only, the conditions that must be validated before proceeding, each with an owner and deadline. Null otherwise |
| `dissenting_evidence` | Signals pointing against the recommendation, each with a source reference |

## Procedure

1. Read each input artifact from the artifact store with spgr-read-artifact.
2. Run the prerequisite check before any synthesis. Confirm three things are present and grounded: a problem statement backed by cited user research, a defined ICP document, and at least one differentiation gap from the competitive matrix that the product can credibly own. If any of the three is missing or unsupported, do not synthesize. Call spgr-escalate with type `missing-input`, name the absent prerequisite, and stop.
3. Weigh the evidence across five dimensions: problem-evidence strength, ICP specificity, differentiation credibility, market-size adequacy for the business model, and feasibility concerns.
4. Select the recommendation. Choose `conditional-go` when evidence for the problem and ICP is strong but a specific risk is high enough to require mitigation first, for example a competitor announcing a directly competing feature or an unproven core mechanic. Choose `no-go` when the research does not support building, and state the reasoning so the decision can be revisited if market conditions change. A no-go is the correct output here, not a phase failure.
5. Collect supporting_evidence and dissenting_evidence in parallel. Every claim carries a source reference back to a discovery artifact. Surface contrary signals alongside the supporting ones. Hiding contrary signals produces overconfident decisions.
6. Identify the top 3 to 5 key_risks, each with likelihood, impact, and a mitigation note. For a `conditional-go`, write the conditions list, each with an owner and deadline. Set conditions to null otherwise.
7. State the differentiation_case as the single defensible claim, traced to the differentiation gap found in step 2.
8. Write the go-no-go artifact with spgr-write-artifact and validate inline with spgr-validate-artifact. Record the recommendation choice and its primary driver with spgr-log-decision.
9. Route to the mandatory human checkpoint. Call spgr-notify-human with `checkpoint_type: go-no-go` and these options: Approve (pipeline advances to PM planning phase), Reject (discovery artifacts archived, project halted), Conditional Approve (pipeline pauses until specified conditions are met). Do not advance the pipeline before the human responds.

## Notes

- Output type is an envelope artifact written via spgr-write-artifact. The `go-no-go` type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Recommendation enum is exactly `go`, `no-go`, or `conditional-go`. The `conditions` field is required and non-null only for `conditional-go`.
- The HIL checkpoint is non-negotiable. The recommendation is never acted on autonomously. The Orchestrator routes the artifact to the human checkpoint, and only an Approve advances to planning.
- Source references on every supporting and dissenting claim are mandatory. An uncited claim is not admissible evidence for this gate.
