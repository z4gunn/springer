---
name: spgr-mine-support-data
description: Produce a support-data analysis artifact from customer support tickets, chat transcripts, and NPS verbatims, surfacing top issue categories by volume and sentiment, recurring feature requests, product failure patterns, churn-risk signals, per-category resolution rate, and a growing-stable-declining trend. Use when the PM agent needs post-launch ground truth on where real users fail before re-prioritizing the backlog, or when the QA agent needs failure-mode evidence from production support volume.
---

# mine-support-data

## Purpose

Post-launch support data is the ground truth of where users fail. Support tickets are actual in-product failures from paying customers, the friction points they cared enough about to seek help for. NPS verbatims at score extremes reveal both retention anchors (promoters) and the most urgent churn risks (detractors). This skill converts unstructured support volume into a prioritized, evidence-grounded backlog signal that the PM agent can act on.

This skill is a consultant output of a user-feedback vertical. Its analysis informs the PM agent's backlog. It does not edit the backlog directly. Recommendations to the PM agent flow through a consultation registered with spgr-tag-vertical-agent. Churn-risk signals trigger an immediate escalation through spgr-escalate.

## Inputs

| Field | Description |
|-------|-------------|
| `support_ticket_export` | CSV, JSON, or structured export of support tickets with subject, body, creation date, resolution status |
| `nps_verbatim_dataset` | Optional NPS response dataset with score and verbatim text |
| `chat_logs` | Optional live chat or bot conversation transcripts |
| `date_filter` | Date range to analyze. Defaults to last 90 days for current state, up to 12 months for trend analysis |
| `minimum_volume_threshold` | Minimum ticket count for a theme to appear in output. Defaults to 3 |

## Outputs

| Artifact | Description |
|----------|-------------|
| `issue_categories` | Top issue categories by ticket volume with percentage share, sentiment, resolution rate, and trend |
| `feature_requests` | Recurring explicit feature requests extracted from ticket text, sorted by frequency |
| `failure_mode_patterns` | Recurring product failure patterns, classified as error, confusion, or dead-end |
| `churn_risk_signals` | Tickets and NPS verbatims indicating churn intent or active migration |
| `nps_breakdown` | Promoter, passive, and detractor counts with top promoter and detractor themes |

## Procedure

1. Read the source files with spgr-read-file. Accept the ticket export, and the NPS dataset and chat logs if present. If no support data is available at all, stop and record this as a gap in discovery coverage, then escalate to the PM agent through spgr-escalate. Do not synthesize support data from other sources.

2. Anonymize before any analysis. Strip PII fields, then run a regex sweep over remaining text for email addresses, phone numbers, and customer or company names in standard positions. Replace each match with a stable placeholder token. No personally identifiable information from ticket text may appear in the output. Verify the sweep on a sample before proceeding.

3. Apply the date filter. Default to the last 90 days for current-state categories. Extend the window up to 12 months only for the trend computation.

4. Run the categorization pass. Classify each ticket into one issue category from the base taxonomy: `onboarding`, `billing`, `performance`, `data-loss`, `missing-feature`, `integration-failure`, `ui-confusion`, `account-management`, `other`. Record the ticket id and a sentiment read (frustration, abandonment, neutral) per ticket.

5. Run the synthesis pass. Aggregate categories by volume and percentage of total. Drop any category below `minimum_volume_threshold`. For each surviving category compute resolution rate (resolved over total) and the trend across the extended window, labeled growing, stable, or declining. Rank categories by volume and sentiment together. A high-volume category described with frustration or abandonment language outranks a high-volume category described in neutral language.

6. Extract feature requests from ticket text with mention count, an urgency read, and example quotes. Extract failure-mode patterns with frequency and a `failure_type` of error, confusion, or dead-end.

7. Analyze NPS verbatims by score band, separately. Treat scores 0 to 6 as detractors and 9 to 10 as promoters. Detractor verbatims reveal churn drivers. Promoter verbatims reveal retention anchors. Preserve top themes from both bands in `nps_breakdown`.

8. Detect churn-risk signals. Flag any ticket or detractor verbatim containing active-churn language, for example "canceling my subscription", "switching to [competitor]", "this is unacceptable", or "I give up". For every churn-risk signal raise an escalation to the PM agent with spgr-escalate. These signals indicate users on the edge of churning and do not wait for the next backlog review.

9. Write the analysis as an envelope artifact with spgr-write-artifact, carrying the header, confidence map, decision log, and version. Run spgr-validate-artifact inline. Record any consequential analysis choice with spgr-log-decision.

10. Register the recommendation to the PM agent through spgr-tag-vertical-agent as a consultation. Do not edit the backlog artifact directly.

## Notes

- Output type is a support-data analysis envelope artifact. Its content schema is registered in a later increment, so envelope-only validation applies for now through spgr-validate-artifact.
- Volume alone does not set priority. Volume combined with sentiment sets priority, per step 5.
- Churn-risk detection is a hard escalation trigger, not an advisory finding. Each signal routes to the PM agent immediately.
- Missing support data is a discovery-coverage gap to flag, not a silent skip. Escalate rather than proceeding with partial coverage assumed complete.
