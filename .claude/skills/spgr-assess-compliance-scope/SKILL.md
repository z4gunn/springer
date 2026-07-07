---
name: spgr-assess-compliance-scope
description: Produce a compliance-scope artifact that names which regulatory frameworks apply to the project and which do not, with rationale, a priority order, and a requirements summary per applicable framework. Use when the Compliance Agent starts a project, or when changed requirements force a scope re-evaluation.
---

# assess-compliance-scope

## Purpose

Determine which regulatory frameworks bind the project and which do not, given what the product does, where it operates, what data it touches, and who its users are. Applying every framework to every project produces compliance theater and wasted effort. Missing a required framework creates legal and financial exposure. This skill makes the determination systematic and traceable, so every downstream compliance artifact (data classification, retention policy, control mapping) inherits a justified scope rather than an assumed one.

## Inputs

| Field | Description |
|-------|-------------|
| `product_description` | What the product does and its target market |
| `user_geographies` | Where the product will be sold and used, by jurisdiction |
| `data_types` | Data collected and processed, including health data, financial data, PII, and payment card data |
| `business_model` | SaaS, consumer app, enterprise, healthcare, or other |
| `prior_scope` | The existing compliance-scope artifact, supplied only on a re-evaluation run |

## Outputs

| Artifact | Description |
|----------|-------------|
| `compliance-scope` | Applicable frameworks with applicability rationale, non-applicable frameworks with exclusion rationale, a priority order separating legally mandatory from competitively required, and a high-level requirements summary per applicable framework |

## Procedure

1. Read each input. If any of product description, user geographies, data types, or business model is missing or contradictory, stop and raise the gap with spgr-escalate rather than assuming a default. Scope cannot be guessed.
2. On a re-evaluation run, read the prior scope artifact with spgr-read-artifact before assessing, so the output records what changed and which frameworks are newly in or out.
3. Evaluate each candidate framework against the inputs and record an explicit applicability or exclusion decision with rationale. Apply these determination rules:
   - GDPR applies to any product that processes personal data of EU residents, regardless of where the company is incorporated. Being a US company is not an exemption.
   - HIPAA applies when the product is a covered entity (healthcare provider, health plan, or healthcare clearinghouse) or a business associate processing PHI on behalf of a covered entity.
   - PCI DSS applies at the level of card data handling. If payment processing is fully delegated to a provider such as Stripe or Braintree and the application never sees raw card data, PCI scope is minimal (SAQ A). Note the SAQ level in the rationale.
   - CCPA applies when the product handles personal information of California residents above the statute's thresholds.
   - SOC 2 is not legally mandated but is effectively required for enterprise SaaS sales, since most enterprise procurement requires a SOC 2 Type II report. Mark it competitively required, not legally mandatory.
4. Assign a priority order that separates legally mandatory frameworks from competitively required ones. State which must be satisfied before launch and which can follow.
5. Write a high-level requirements summary for each applicable framework, enough to scope downstream compliance work without restating the regulation.
6. Record the consequential scope calls with spgr-log-decision, including any framework that is close to the applicability line and the reasoning for the call made.
7. Write the artifact with spgr-write-artifact and validate it inline with spgr-validate-artifact before the write completes.
8. When the assessment turns on a legal interpretation the skill cannot settle, or when an input implies a framework with major build impact (for example HIPAA or PCI at full scope), notify the human with spgr-notify-human, since compliance scope is a human flag gate.
9. On a re-evaluation run, if a framework becomes newly applicable, raise it with spgr-escalate and notify the human with spgr-notify-human so the scope change is reviewed before downstream work proceeds.

## Notes

- The compliance-scope artifact type is not yet in the schema registry. It is written via spgr-write-artifact and its registered schema is added in a later build increment. Until then, validation confirms the shared envelope only.
- This skill determines scope. It does not write the data classification, retention policy, or control mappings. Those are separate compliance skills that consume this artifact.
- A compliance flag is a required human-in-the-loop gate, so a newly applicable framework or a high-impact determination always reaches the human rather than being resolved silently.
