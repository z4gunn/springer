---
name: spgr-market-sizing
description: Produce a market-sizing artifact estimating TAM, SAM, and SOM with a bottom-up calculation, a top-down cross-check, and a viability signal on whether the obtainable market justifies the build cost. Use when the Discovery Agent must ground the go/no-go decision in market economics, or when geography or business model changes force a re-estimate.
---

# market-sizing

## Purpose

Size the addressable market so the go/no-go decision rests on economics, not user pain alone. Build the estimate bottom-up from the ICP, count the matching entities, multiply by annual revenue per account, then run a top-down industry-report estimate as a cross-check. A small but defensible SOM for a specific niche is worth more than an inflated TAM that includes customers the product will never reach. Every number carries a cited source and every assumption carries a confidence level, so a downstream reader can challenge any figure rather than accept it.

This is a Phase 1 discovery skill. It writes no code. It requires web access, and every factual claim carries a source.

## Inputs

| Field | Description |
|-------|-------------|
| `problem_space` | The problem being solved, used to scope which industries and user types to size |
| `icp_document` | The build-icp output, the target customer used for the bottom-up SOM estimate |
| `geography` | Geographic scope, global or specific regions or countries |
| `business_model` | Pricing model and expected ARPU, used to convert entity counts to revenue |
| `time_horizon` | Year for the SOM estimate, typically 3 to 5 years from launch |

Read inputs with spgr-read-artifact for the ICP and spgr-read-file for any supporting input.

## Outputs

| Artifact | Description |
|----------|-------------|
| `market-sizing` | An envelope artifact carrying TAM, SAM, and SOM, each with value, unit, methodology, sources, and assumptions, plus a global assumptions list, a viability signal, and viability notes |

Write the artifact with spgr-write-artifact and validate it inline with spgr-validate-artifact. The content body matches this shape:

```
{
  geography, time_horizon, business_model,
  tam: { value, unit, methodology, sources, assumptions },
  sam: { value, unit, methodology, sources, assumptions },
  som: { value, unit, methodology, sources, assumptions },
  assumptions: [ { assumption, confidence: "high"|"medium"|"low", impact_if_wrong } ],
  viability_signal: "strong"|"marginal"|"insufficient",
  viability_notes
}
```

## Procedure

Run two passes. The first gathers raw data. The second applies the calculation framework with explicit arithmetic.

1. Gather raw data. Use spgr-search-web for industry reports, population statistics, and ARPU benchmarks, and with `search_context: pricing` for competitor pricing signals. Record every figure with its source URL and the retrieval date. Do not carry a number forward without a citation.

2. Build the bottom-up estimate from the ICP. This is the primary methodology. Count the number of ICP-matching entities, then apply the formulas:
   - TAM = total_population x addressable_fraction x ARPU_annual
   - SAM = TAM x distribution_reach_fraction
   - SOM = SAM x realistic_capture_fraction_in_time_horizon
   Show the arithmetic for each line. Tie distribution_reach_fraction to the geography and the product's distribution model, and tie realistic_capture_fraction to the team, budget, and competition over the time horizon.

3. Run the top-down cross-check. Estimate the market a second way using the best available industry report multiplied by an expected market-share percentage. Use this only as a sanity check, never as the primary number.

4. Compare the two estimates. If bottom-up and top-down differ by more than 3x, flag the discrepancy in viability_notes and name the single assumption that drives the gap.

5. State every assumption explicitly in the global `assumptions` list. Give each a confidence level of high, medium, or low and an `impact_if_wrong` note. Distinguish revenue addressability from user addressability, since a large free user base does not imply a large TAM when monetization is constrained.

6. Set the viability signal. Compare SOM against the build cost implied by the business model. If SOM does not justify the cost to build, for example a 500K ARR ceiling for a product that would cost 2M to build, set `viability_signal` to insufficient and state the no-go signal in viability_notes. Use marginal when the margin is thin and strong when SOM clears the build cost with headroom.

7. Validate and version. Call spgr-validate-artifact on the result. If any TAM, SAM, or SOM figure lacks a citation, or any assumption lacks a confidence level, do not emit the artifact. Fix the gap or, if the gap is in the input, stop and call spgr-escalate with the precise list of what is missing. Record the methodology choice and the viability verdict with spgr-log-decision, then version the artifact with spgr-version-artifact.

## Escalation

- Missing or contradictory input, for example no ICP, no ARPU, or a geography that conflicts with the distribution model. Stop and call spgr-escalate. Do not fill the gap with an assumed figure.
- No credible source for a population count or ARPU benchmark after a genuine search. Call spgr-escalate rather than inventing a number.
- A viability_signal of insufficient is a potential no-go signal. Surface it to the Discovery Agent and call spgr-notify-human, since this is a decision that requires judgment.

## Notes

- Output type is an envelope artifact written via spgr-write-artifact. No content schema is registered for market-sizing yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Bottom-up is the primary methodology. Top-down is a cross-check only.
- Every factual claim carries a source with a retrieval date. A figure without a citation does not enter the artifact.
- Each assumption carries a confidence level and an impact-if-wrong note, so any number can be challenged and revised when new data arrives.
