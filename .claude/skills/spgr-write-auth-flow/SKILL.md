---
name: spgr-write-auth-flow
description: Produce an auth-flow artifact that specifies each authentication flow (login, logout, token refresh, password reset, OAuth/OIDC callback, MFA) at the sequence level, with the happy path and every documented failure path, plus a synchronized Mermaid sequence diagram per flow. Use when the Auth Agent has an approved auth model and provider documentation and must define the implementable, auditable flow specification before any auth code is written, or when an auth flow changes and its specification and diagram must be revised together.
---

# write-auth-flow

## Purpose

Write the sequence-level specification for each authentication flow so a developer has an unambiguous target to implement against and the Auth Agent has a concrete artifact to audit the implementation against. Auth flows carry the highest density of subtle security bugs, so the value of this skill is in forcing every unhappy path to be named and handled before code exists. An undocumented branch is a branch a security researcher finds later. Each flow is captured both as step-by-step text and as a Mermaid sequence diagram generated from the same source so the visual never drifts from the specification.

## Inputs

| Field | Description |
|-------|-------------|
| `auth-model` | The approved auth model document from spgr-design-auth-model, read via spgr-read-artifact. Names the provider, token strategy, session model, and identity decisions this skill must conform to. |
| `provider-docs` | Documentation for the selected auth provider, covering its callback, token, and revocation endpoints and constraints. |
| `flow-requirements` | Product requirements per flow: social login providers in scope, required MFA factors, session and token duration targets, lockout policy inputs. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `auth-flow` | One auth-flow artifact covering every in-scope flow. Each flow holds a named happy path, an enumerated set of failure paths with their handling, and a Mermaid sequence diagram. Flows in scope: email/password login, OAuth/OIDC callback, token refresh, logout, password reset, and MFA. |

## Procedure

1. Read the auth-model artifact with spgr-read-artifact and confirm it is present and validates. If it is missing, fails validation, or omits a decision a flow depends on (provider, token type, session model), stop and call spgr-escalate with the precise list of what is missing. Do not assume a provider or token strategy.

2. Confirm flow-requirements name every flow in scope and supply the inputs each needs: social providers for OAuth, factors for MFA, duration targets for refresh and reset. If a required input is absent or contradicts the auth model, call spgr-escalate rather than choosing a default.

3. For each flow, write the happy path as an ordered sequence of steps between the actor, client, application, and provider. Name the participant on each step so the text maps one to one to the diagram.

4. For each flow, enumerate the failure paths and specify the handling for each. Treat a missing failure path as an incomplete flow, not a finished one. Cover at least:
   - Email/password login: wrong password, account locked, unverified email. Specify rate limiting after N failed attempts, the lockout policy, and error wording that is generic enough not to reveal whether the email exists.
   - OAuth/OIDC callback: state mismatch, code exchange failure, account linking conflict. Document PKCE code verifier and challenge generation and verification explicitly. PKCE is mandatory for every OAuth and OIDC flow regardless of client type.
   - Token refresh: refresh token expired, refresh token revoked, reuse detection.
   - Logout: local session clearing, provider session revocation, multi-device logout.
   - Password reset: request, email delivery, token validation, token expiry. Reset tokens carry an explicit expiry of 15 to 60 minutes and are single-use. Document the invalidation mechanism so a used or expired token cannot be replayed.
   - MFA: enrollment, challenge, and recovery code flow.

5. Generate one Mermaid sequence diagram per flow from the written steps so the diagram and text share a single source. Include both the happy path and the failure branches in the diagram via alt and opt blocks. Verify each diagram parses as valid Mermaid before write.

6. Tag the Auth vertical for review with spgr-tag-vertical-agent on any flow that deviates from the auth model or the provider's documented sequence, and record the recommendation. Use spgr-log-decision to capture consequential choices (lockout thresholds, token lifetimes, account-linking rules) with their rationale and rejected alternatives.

7. Write the artifact with spgr-write-artifact. Because auth-flow is not yet a registered schema type, the envelope header, confidence map, and decision log still apply, and the content is validated against the auth-flow schema once it is registered in a later build increment.

## Notes

- The auth-flow artifact is written via spgr-write-artifact. Its registered JSON Schema is added to the schema registry in a later build increment, so until then the content fields are not validated by spgr-validate-artifact even though the shared envelope still is.
- Mark each flow's confidence as confirmed, proposed, or needs-human-input. A flow that depends on an unresolved auth-model decision stays needs-human-input rather than being guessed.
- Keep this artifact and the auth model in sync. When a flow changes, revise the text and regenerate its Mermaid diagram in the same write, then version with spgr-version-artifact.
