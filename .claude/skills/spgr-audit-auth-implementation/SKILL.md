---
name: spgr-audit-auth-implementation
description: Produce an auth-implementation audit report that checks implemented auth code against the auth model, auth flow specs, and RBAC policy, returning a PASS or GATE verdict that blocks the architecture confirmation gate on any Critical or High finding. Use when the Auth Agent must confirm the auth implementation before a release.
---

# audit-auth-implementation

## Purpose

Close the loop between the auth specification and the actual implementation. Specifications define intent, implementation defines reality, and auth bugs are high-severity by definition. They are found most cheaply during audit, not in production. Run this audit to surface the gaps, for example a token in localStorage when the auth model required httpOnly cookies, a missing PKCE step, or a permission check that bypasses the service layer.

This skill operates the Auth Agent in auditor and gate mode. The audit is code-level and evidence-based. Every finding names a specific file path and line and includes a remediation recommendation. A general description is not a finding. "Session tokens may be vulnerable" is not acceptable. "src/middleware/session.ts:47 stores the refresh token in localStorage, violating the auth model spec's httpOnly cookie requirement" is. Critical and High findings block the architecture confirmation gate.

## Inputs

| Field | Description |
|-------|-------------|
| `auth-model` | The auth model document: token storage, session strategy, credential handling, MFA stance. Read with spgr-read-artifact or spgr-read-file. |
| `auth-flow-specs` | The auth flow specifications: login, logout, refresh, password reset, OAuth or OIDC flows including PKCE where required. Read with spgr-read-artifact or spgr-read-file. |
| `rbac-policy` | The RBAC policy defining roles, permissions, and the enforcement layer where each permission is checked. Read with spgr-read-artifact or spgr-read-file. |
| `auth-source` | The auth-related source code: middleware, session handlers, token logic, permission checks, auth endpoints. Located with spgr-search-codebase and read with spgr-read-file. |
| `release-scope` | Optional. The auth surfaces in the pending release, used to scope the gate verdict to what is shipping. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `auth-implementation-audit` | Audit report envelope artifact written via spgr-write-artifact. Carries per-finding deviations with exact file and line references, a severity per finding, a remediation per finding, the blocking findings, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Load the auth model, the auth flow specs, and the RBAC policy first, because every finding is a deviation measured against one of them. If any of the three specs or the auth source is missing, stop and raise spgr-escalate with the precise list of what is absent. Do not infer the intended auth behavior from habit, because an audit against an assumed spec produces findings that cannot be trusted.

2. Audit token storage and session handling against the auth model. Trace where each token (access, refresh, session) is written and read. Flag any storage location that deviates from the model, for example a refresh token in localStorage or sessionStorage when the model required an httpOnly, Secure, SameSite cookie. Confirm session expiry, idle timeout, and rotation match the model. An unrotated refresh token is a deviation that creates security risk and is High.

3. Audit the auth flows against the flow specs. Confirm each specified step is implemented. For an OAuth or OIDC authorization-code flow that requires PKCE, confirm the code challenge and verifier are generated and validated. A missing PKCE implementation is a vulnerability with an active exploit path and is Critical. Confirm logout invalidates the server-side session, and confirm password reset uses single-use, time-bound tokens.

4. Audit RBAC enforcement against the policy. For each permission, trace where it is checked and confirm the check sits at the enforcement layer the policy names, not a layer that can be bypassed. A permission check that bypasses the service layer or a route that reaches a privileged operation without a check is a privilege-escalation path and is Critical. Confirm there is no horizontal escalation path where a user can act on another user's resource by changing an ID.

5. Audit auth-endpoint hardening. Confirm rate limiting is present on login, refresh, and password-reset endpoints. Missing rate limiting on auth endpoints is High. Flag error messages that leak account existence (a distinct response for a known versus unknown account) as Medium. Flag a missing MFA requirement on admin endpoints where the model required it as Medium.

6. Classify every finding by severity using the spec thresholds. Critical is a vulnerability with an active exploit path (missing PKCE, credential storage in an insecure location, a privilege-escalation path). High is a deviation from spec that creates security risk if exploited (missing rate limiting on auth endpoints, an unrotated refresh token). Medium is an implementation-quality issue (account-existence leak, missing MFA on admin endpoints). Low is a minor deviation with negligible security impact. Each finding carries its exact file path and line and a remediation recommendation.

7. Set the verdict. The blocking threshold is any open Critical or High finding on an in-scope auth surface. If `release-scope` is supplied, score the verdict against only the surfaces in scope. The verdict is GATE if any Critical or High finding is open, otherwise PASS. A GATE verdict blocks the architecture confirmation gate, so the architecture artifact cannot be marked confirmed while a Critical or High auth finding is open.

8. Write and validate the report. Write the `auth-implementation-audit` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and each blocking finding with spgr-log-decision.

9. Route remediation and surface the gate. For each finding owned by a developer agent (a backend token path, a frontend storage choice, a middleware check), route the remediation through a consultation with spgr-tag-vertical-agent rather than editing that agent's code or artifact directly. On a GATE verdict, surface the decision to the human gate with spgr-notify-human, since an open Critical or High auth finding is a security flag.

10. Propose SAST enforcement for recurring patterns. For each Critical or High pattern this audit catches (insecure token storage, missing PKCE, an unenforced permission check), recommend a SAST rule that catches the pattern in CI before it reaches the audit stage, routed to the DevOps or Security agent through spgr-tag-vertical-agent. Do not author or run the scanner here, only record the recommendation in the report.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version). Still call spgr-validate-artifact.
- Blocking threshold: any open Critical or High finding on an in-scope auth surface yields a GATE verdict, which also blocks the architecture confirmation gate. Medium and Low findings are reported but do not gate on their own.
- Every finding names an exact file path and line and carries a remediation recommendation. A general description without a code reference is not a valid finding.
- This audit reads and reports only. It does not change token storage, add a PKCE step, add a permission check, or write a SAST rule. Recommendations to other agents flow through spgr-tag-vertical-agent.
