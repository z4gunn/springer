---
name: spgr-implement-state-management
description: Implement client-side state management for one feature following the state management pattern fixed in the architecture ADR, producing feature-scoped store slices, data-fetching queries with explicit cache invalidation, mutations with loading and error handling, optimistic updates with a rollback path, and a documented state shape. Use when the Frontend Developer or Mobile Developer agent needs to wire a feature's state against the approved pattern and the failing acceptance tests for that feature already exist.
---

# implement-state-management

## Purpose

Implement the client-side state for one feature using the exact state management pattern recorded in the architecture ADR, for example Redux, Zustand, React Query, MobX, or TCA. Following the approved pattern keeps the client architecture coherent and prevents competing patterns that produce unpredictable behavior, duplicate fetching, and defects that are hard to reproduce. The output is source code, not an envelope artifact. It is verified by spgr-run-tests and CI, not by a registered schema.

## Inputs

| Field | Description |
|-------|-------------|
| `api-contract` | The endpoints and request and response schemas the feature consumes. Read the api-spec artifact via spgr-read-artifact (OpenAPI), produced by spgr-write-api-spec. |
| `component-tree` | Which components need access to which state, used to decide local versus global placement. |
| `state-requirements` | What must persist across navigation versus what is ephemeral, plus which interactions require immediate UI feedback. |
| `approved-pattern` | The state management pattern fixed in the architecture ADR. Read it via spgr-read-artifact (adr or architecture-decision schema). Read the concrete library and pinned version from the tech-stack-decision artifact. |
| `acceptance-tests` | The failing acceptance tests for the feature, produced by spgr-write-acceptance-test against criteria from spgr-write-acceptance-criteria. These define the behavior the state must satisfy. |

## Outputs

| Artifact | Description |
|----------|-------------|
| State implementation | Feature-scoped store slices or the pattern equivalent, written to disk via spgr-write-file next to the feature per project convention. |
| Data-fetching queries | Read queries with explicit caching and invalidation rules. |
| Mutations | Write operations that carry loading and error state, with optimistic updates and a rollback path where the UX requires immediate feedback. |
| State shape documentation | The state shape and any non-obvious shape decision documented in code comments at the slice. |

## Procedure

1. Read the approved pattern from the ADR via spgr-read-artifact, and read the api-contract and the failing acceptance tests. If the ADR does not name a state management pattern, or names a pattern the tech-stack-decision does not pin to a library and version, stop and escalate (see Notes). Do not pick a pattern.
2. Confirm the failing acceptance tests for the feature exist and fail before you write any implementation. If they do not exist, stop and escalate to the QA agent rather than writing implementation against an unwritten contract.
3. Place state by concern. Keep local concerns in component-local state, including form input, toggle state, and transient UI state. Put only shared concerns in the global store, including the authenticated user, feature flags, and cross-feature data. Add a piece of global state only when a shared concern in the component-tree requires it, because every global entry raises complexity.
4. Implement the data-fetching queries against the api-contract. Write an explicit cache invalidation rule for each query. For every mutation, name which queries it invalidates or updates on success. Do not leave invalidation implicit.
5. Implement each mutation with loading and error state. Where the state-requirements call for immediate feedback, add an optimistic update, and pair it with a rollback path that reverts the UI to the pre-optimistic state when the mutation fails. An optimistic update without a rollback path is incomplete.
6. Apply YAGNI. Build only the slices, queries, and mutations the acceptance tests and the api-contract require. Do not add state the feature is not required to hold.
7. Add the pattern's development-only debugging integration, for example Redux DevTools or its equivalent for the chosen pattern, gated to development builds so it does not ship to production.
8. Document the state shape in code comments at the slice. When a shape decision involves a non-obvious choice, record it via spgr-log-decision and write the feature-level ADR for it via spgr-write-adr.
9. Run the feature's acceptance and unit tests via spgr-run-tests. Confirm the previously failing tests now pass for the right reason. Reach zero lint errors via spgr-lint-code and format the changed files via spgr-format-code before commit. Keep the change to one logical change per commit.
10. Write each file via spgr-write-file, which enforces read-before-write and a post-write checksum.

## Notes

- This skill produces source code. Verification is by spgr-run-tests and CI, not by an envelope schema. Reference artifact schemas through spgr-read-artifact and spgr-validate-artifact rather than inlining field lists.
- Follow the pattern fixed in the architecture ADR exactly. Do not introduce a different pattern for convenience. The approved architecture is an immutable constraint. If the feature cannot be satisfied within the approved pattern, escalate via spgr-escalate rather than deviating.
- Escalate via spgr-escalate when the ADR names no state management pattern or the tech-stack-decision does not pin it to a library and version, when the api-contract and the state-requirements disagree on what data the feature holds, or when an optimistic update is required but the api-contract gives no way to detect failure for rollback. Return the precise list of what is missing rather than guessing.
- When a state shape decision touches a vertical concern such as where the authenticated user lives, consult the owning vertical via spgr-tag-vertical-agent before finalizing.
