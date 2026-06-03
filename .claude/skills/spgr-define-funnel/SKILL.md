---
name: spgr-define-funnel
description: Produce a funnel-definition artifact that specifies each conversion funnel as an ordered event sequence with entry criteria, an explicit conversion window, completion criteria, and segmentation dimensions, then generate the platform-specific funnel report config (Amplitude, Mixpanel, etc.) from that spec. Use when the Analytics Agent must define the conversion funnels for a product's core journeys against a confirmed event taxonomy, or when the PM agent needs funnel definitions to set the success metric for a story.
---

# define-funnel

## Purpose

Produce a deterministic, reproducible definition of every conversion funnel that measures user progression through a core product journey. A funnel surfaces the highest-drop-off step, the optimization opportunity worth fixing. An undefined funnel produces conversion numbers that cannot be compared over time or segmented consistently, so it cannot answer whether a change improved conversion. This skill is an Analytics vertical output. It defines funnels by referencing events that already exist in the confirmed event taxonomy, and it emits the analytics-platform report config so the funnels are measured the same way every run.

## Inputs

| Field | Description |
|-------|-------------|
| `core-journeys` | Core user journeys from the product spec or PRD that need conversion measurement. Read upstream artifacts with `spgr-read-artifact`. |
| `event-taxonomy` | The confirmed event taxonomy. Every funnel step must map to one event in this taxonomy. Read with `spgr-read-artifact`. |
| `business-goals` | Which conversions are most valuable, used to order funnels and name each funnel's business goal. |
| `analytics-platform` | The target platform (Amplitude, Mixpanel, etc.) whose report config the procedure generates. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `funnel-definition` | Envelope artifact listing each funnel with name, business goal, ordered event sequence (event name, required properties, step label), entry criteria, conversion window, completion criteria, and segmentation dimensions. Written via `spgr-write-artifact`. |
| platform funnel config | Source or config files (one per funnel report) generated from the definition, in the target platform's format. Written via `spgr-write-file`, verified in CI or by `spgr-run-tests`. |

## Procedure

1. Read the core journeys, business goals, and the event taxonomy with `spgr-read-artifact`. Order the journeys by business value so the most valuable conversions are defined first.
2. For each journey, define a funnel: a name, the business goal it measures, and an ordered event sequence. Each step carries the event name, the required event properties, and a human-readable step label.
3. Map every step to a specific event that exists in the taxonomy. If a step has no backing event (for example "user sees the pricing page" with no `pricing_page_viewed` event), do not invent one. Stop and escalate (see step 7).
4. Define steps at the level of user intent, not UI steps. Collapse repeated views of the same screen into a single step. A user refreshing a page three times stays at one funnel step.
5. Set an explicit conversion window per funnel (for example "within 7 days of signup"). Never leave a funnel open-ended. An open window counts any completion regardless of time and inflates the conversion rate. Set entry criteria (what qualifies a user to enter) and completion criteria (which event marks successful conversion).
6. List the segmentation dimensions each funnel supports (for example plan, platform, traffic source), restricted to event properties that exist in the taxonomy for the relevant steps.
7. If a journey references a step with no backing event, the conversion window is undefined or cannot be agreed, or business goals do not map to a measurable completion event, raise `spgr-escalate` with the precise gap. Do not fill the gap with an assumed event or an open window. When the missing or contradictory input belongs to the event taxonomy, route the recommendation back to the taxonomy's owning agent through `spgr-tag-vertical-agent` rather than editing that artifact.
8. Record each consequential choice (conversion-window length, intent-level step collapsing, which completion event counts) with `spgr-log-decision` on the artifact.
9. Write the funnel-definition artifact with `spgr-write-artifact` and validate it inline with `spgr-validate-artifact`. Version it with `spgr-version-artifact` on revision.
10. Generate the platform-specific funnel report config from the confirmed definition, one config per funnel, and write it with `spgr-write-file`. Verify the generated config loads or passes its check in CI or via `spgr-run-tests`.

## Notes

- Output type: `funnel-definition` is an envelope artifact, and the platform report config is source or config output. The `funnel-definition` content schema is registered in a later increment, so `spgr-validate-artifact` applies envelope-only validation for now (header, confidence map, decision log, version).
- The funnel-definition does not edit the event taxonomy. A recommendation to add or change an event flows to the taxonomy's owning agent through `spgr-tag-vertical-agent` as a consultation.
- Conversion windows are mandatory and explicit. An open-ended funnel is not a valid output.
- Every step references an event by name from the confirmed taxonomy. No funnel step exists without a backing event.
