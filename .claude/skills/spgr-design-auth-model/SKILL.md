---
name: spgr-design-auth-model
description: Produce an auth-model artifact that recommends an identity approach for the project, covering provider selection, token strategy, session management, MFA, and access control, each chosen against a scored comparison of the top candidate combinations rather than by habit. Use when the Auth Agent has user types, compliance constraints, product identity requirements, and the tech stack and must settle the auth model before architecture or any auth implementation begins.
---

# design-auth-model

## Purpose

Decide the project's auth model systematically and record the decision as an auth-model artifact. The auth model is a consequential early architecture choice. A fit-for-purpose choice matches the project risk profile, user base, and operational constraints without adding complexity. A poor choice ships insecure identity infrastructure or carries migration debt. This skill forces a scored comparison of candidate provider and token combinations before recommending one, and documents every tradeoff rather than defaulting it.

## Inputs

| Field | Description |
|-------|-------------|
| `user-types` | User types and personas, including who authenticates and their trust levels |
| `compliance-constraints` | Compliance requirements affecting identity, such as HIPAA, GDPR, or SOC 2 |
| `product-requirements` | Identity-facing product needs, such as SSO, social login, MFA, and API access |
| `tech-stack` | Selected or proposed stack, which constrains provider compatibility |

## Outputs

| Artifact | Description |
|----------|-------------|
| `auth-model` | Recommendation covering provider, token strategy, session management, MFA strategy, access control approach, and the scored comparison that supports the choice |

## Procedure

1. Read the inputs through spgr-read-artifact for any that arrive as artifacts (PRD, NFR, tech-stack-decision). If user types, compliance constraints, product identity requirements, or the tech stack are missing or contradictory, stop and raise spgr-escalate with a precise list of what is needed. Do not assume a trust model or a compliance posture.

2. Derive the identity requirement set from the inputs: required factors, federation needs (SSO, social login), API access patterns, regulated data classes, and expected user scale. These drive every later choice.

3. Select the top three candidate provider and token-strategy combinations. Default to managed providers (for example Clerk, Auth0, Supabase Auth). Include a custom-identity option only when an input justifies it: cost at scale, a regulatory requirement for on-premises, or a required capability the managed providers cannot add via extension.

4. Score each candidate against a comparison matrix with these criteria: security, operational complexity, cost, and compliance fit. Record each cell with a short evidence note. The recommended candidate is the one the matrix supports, not the most familiar.

5. Fix the token strategy and document its tradeoff explicitly. For storage, state the chosen option and its exposure: httpOnly cookies resist XSS but need CSRF mitigation through SameSite=Strict and CSRF tokens, while localStorage resists CSRF but is exposed to XSS. Record JWT versus opaque session tokens, expiry windows, and refresh-token rotation policy. The choice is documented, never defaulted.

6. Fix session management (stateful versus stateless) and the MFA strategy (required or optional, supported factors), each traced to a requirement from step 2.

7. Choose the access control approach. Default to RBAC. Recommend ABAC only when RBAC cannot express the required permission complexity without an unmanageable number of roles, and record that justification.

8. If any choice touches a compliance or security constraint that needs specialist sign-off, consult through spgr-tag-vertical-agent before finalizing, and fold any required amendment into the artifact.

9. Record each consequential choice with spgr-log-decision, capturing the decision, its rationale, the alternatives rejected, and the downstream impact.

10. Write the auth-model artifact with spgr-write-artifact, which applies the shared envelope, per-section confidence signals, and inline validation. Mark each section confirmed, proposed, or needs-human-input. If a provider or compliance decision requires a human gate, route it through spgr-notify-human before the artifact is treated as confirmed.

## Notes

- The auth-model artifact type is not yet in the schema registry. It is written via spgr-write-artifact, and its registered schema is added in a later build increment. Until then, validate the envelope through spgr-validate-artifact and treat the body fields in this skill as the field contract.
- Confidence signals carry the open decisions. Mark a section needs-human-input when an input gap blocks a definitive recommendation, rather than guessing.
- Keep this artifact upstream of spgr-write-auth-flow and spgr-write-rbac-policy. It sets the model those skills implement.
