---
name: spgr-write-ab-test-spec
description: Produce an ab-test-spec artifact that pre-registers an A/B experiment before any code is written, fixing the hypothesis, control and treatment arms, user-level assignment logic, sample size with significance level and power, the single primary success metric, guardrail metrics, expected duration, and win, lose, and inconclusive decision rules. Use when the Analytics Agent must define an experiment before it runs so the result is trustworthy and not p-hacked, or when the Feature Flag Agent needs the assignment logic and computed duration to back a test flag.
---

# write-ab-test-spec

## Purpose

Pre-register an A/B experiment as a typed artifact before the experiment runs. An experiment without a spec invites p-hacking: stopping early when the result looks favorable, or slicing the data until a subgroup appears to win. The spec commits, in advance, to what success means, how the sample is assigned, how long the test runs, and what the decision rules are. That commitment is what makes the result trustworthy.

This is the Analytics vertical operating as a consultant. The spec is an envelope artifact the Analytics Agent owns. Where the experiment is implemented through feature flags, the assignment logic and computed duration flow to the Feature Flag Agent through a registered consultation, not by editing that agent's artifacts.

## Inputs

| Field | Description |
|-------|-------------|
| `hypothesis` | The change, its predicted direction, and the reason it should work. Must be specific, testable, and falsifiable. |
| `primary_metric` | The single metric that determines the winner. One metric only. |
| `baseline_rate` | The current conversion rate for the primary metric, used for sample size calculation. |
| `mde` | Minimum detectable effect: the smallest improvement worth detecting. |
| `event_taxonomy` | The event-taxonomy artifact (read via spgr-read-artifact) the primary and guardrail metrics map to. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `ab-test-spec` | Envelope artifact written via spgr-write-artifact, holding the hypothesis, control and treatment arms, assignment logic, sample size calculation, primary metric and measurement method, guardrail metrics, expected duration, and win, lose, and inconclusive decision rules. |
| `consultation` | When the experiment runs on feature flags, a spgr-tag-vertical-agent consultation to the Feature Flag Agent carrying the assignment logic and the computed expected duration. |

## Procedure

1. Read the inputs. Read the event-taxonomy artifact with spgr-read-artifact and confirm the primary metric and every guardrail metric maps to a defined event. If a metric has no defined event, stop and escalate (step 9).
2. State the hypothesis as a single specific, falsifiable claim that names the change, the predicted direction, and the reason. Reject a vague or non-falsifiable hypothesis and escalate for a rewrite.
3. Define the control arm and each treatment arm, describing exactly what each arm experiences.
4. Define the assignment logic. Require user-level randomization so the same user always sees the same arm. Reject session-level assignment unless the input gives an explicit reason, because within-user contamination inflates variance and novelty effects bias the result. Record the randomization unit and the split ratio.
5. Compute the sample size from `baseline_rate`, `mde`, the significance level (default alpha 0.05, two-sided), and statistical power (default 0.80). Derive the per-arm sample size, the total sample size, and the expected duration from the project's measured traffic to the randomization point. Record every parameter so the calculation is reproducible.
6. Fix the primary success metric and its measurement method against the event taxonomy. Exactly one primary metric determines the winner.
7. Define the guardrail metrics: the metrics that must not degrade. State the per-guardrail threshold. A guardrail breach stops the experiment regardless of the primary-metric result, so a win on the primary metric that degrades a guardrail is not a win.
8. Write the decision rules. State the win, lose, and inconclusive criteria evaluated only at the pre-determined sample size, and the action taken in each case. Forbid stopping at a p-value threshold before the sample size is reached, because early stopping at p < 0.05 inflates the false-positive rate.
9. Validate and route. Write the artifact with spgr-write-artifact and run spgr-validate-artifact inline. Record consequential choices with spgr-log-decision. If the experiment runs on feature flags, open a consultation to the Feature Flag Agent with spgr-tag-vertical-agent carrying the assignment logic and expected duration. On missing input, a non-falsifiable hypothesis, an unmapped metric, or insufficient traffic to reach significance in an acceptable window, stop and raise spgr-escalate with the precise list of what is missing rather than filling the gap with an assumption.

## Notes

- Output type is a spec envelope artifact (`ab-test-spec`). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (it still checks the header, confidence map, decision log, and version).
- Assign at the user level. Reject session-level assignment unless an explicit reason is given in the input.
- Run to the pre-determined sample size, never to a p-value threshold.
- A guardrail breach overrides a primary-metric win and stops the experiment.
- Hand the assignment logic and computed duration to the Feature Flag Agent through a consultation. Do not edit that agent's artifacts directly.
- Revisions go through spgr-version-artifact. A change to the hypothesis, primary metric, or sample size is a scope change and routes to spgr-escalate.
