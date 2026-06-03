---
name: spgr-write-contract-test
description: Produce consumer-driven contract tests between internal service pairs using the Pact protocol, where the consumer publishes a pact file describing the interactions it expects and the provider verifies its implementation against that pact in its own CI pipeline, plus a can-i-deploy pre-deployment gate and a contract coverage report over the service topology. Use when the QA agent owns contract coverage for the service pairs in the system diagram, when the Backend Developer agent implements provider verification in a provider's test suite, or when the API Design agent checks that pact interactions match the published API spec.
---

# write-contract-test

## Purpose

Catch cross-service API drift in each service's own CI pipeline without co-deploying the services. The consumer defines the contract first, writing tests against the Pact mock server that generate a pact file describing the request and response shapes it depends on. The provider then replays that pact against its real implementation and confirms it can satisfy every interaction. The direction of authority runs from consumer to provider, so a provider cannot quietly ship a response change the consumer has not agreed to. Contract tests cover only the shape of the interface, request format, response format, status codes, required fields, and data types. They do not test business logic, which stays with unit and integration tests.

## Inputs

| Field | Description |
|-------|-------------|
| `provider_api_spec` | OpenAPI or equivalent spec for the provider service. |
| `consumer_interactions` | The request and response interactions the consumer expects, documented or derived from the consumer's existing integration tests. |
| `service_topology` | Which services consume which providers, taken from the system diagram. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Consumer contract test | Source code in the consumer codebase that drives the Pact mock server and generates the pact file. |
| Pact file | Machine-readable contract describing each expected interaction, versioned alongside the consumer application. |
| Provider verification test | Source code in the provider codebase that replays the pact against the real provider and confirms every interaction. |
| Pact broker registration | The pact file published to the central Pact broker so both pipelines can reach it. |
| Contract coverage report | Per service pair in the topology, whether a contract test is defined, surfacing pairs with no contract as silent failure risks. |

## Procedure

1. Read the provider API spec, the consumer interactions, and the service topology with spgr-read-artifact, and read any existing consumer integration tests with spgr-read-file. If a provider has no spec, a consumer interaction contradicts the spec, or the topology does not say which service consumes which, stop and raise it with spgr-escalate rather than inferring the interface shape.

2. Confirm each target pair is an internal pair where both sides are owned and can be updated. Do not write a contract test for a third-party external API, a payment processor, an SMS or email provider, and so on. Note those as out of scope and direct them to a provider sandbox or test account instead.

3. Write the consumer contract test first, against the Pact mock server, before any provider verification exists. Model only the interactions the consumer actually uses in production. Each interaction represents one specific scenario, not a comprehensive sweep of every possible request permutation. Run the consumer test with spgr-run-tests and confirm it generates the pact file.

4. Cross-check each generated interaction against the provider API spec. When an interaction's request or response shape, status code, or required fields diverge from the spec, consult the API Design specialist with spgr-tag-vertical-agent before publishing, and record the spec-pact discrepancy.

5. Publish the pact file to the Pact broker so both pipelines can reach it. Version the pact alongside the consumer application. When the consumer's expected interactions change, publish a new pact version so the provider must re-verify, which is the mechanism that catches a breaking provider change before co-deployment.

6. Write the provider verification test in the provider codebase. It pulls the pact from the broker, replays every interaction against the real provider implementation, and reports each interaction as verified, failed with the specific mismatch detail, or pending. Run it with spgr-run-tests.

7. Wire the contract tests into CI on both sides, the consumer pipeline after any change to its outbound API calls and the provider pipeline after any change to its API responses.

8. Integrate a can-i-deploy check into the CD pipeline as a pre-deployment gate. Before deploying any service to staging or production, query the broker to confirm that every pact involving the new version is verified. Block the deployment when verification is missing or failing.

9. Generate the contract coverage report by walking every consumer-provider pair in the system diagram and recording whether a contract test is defined for it. Surface the gaps. As the service count grows, render a contract dependency graph showing the consumer-provider relationships and the current verification status of each, so the blast radius of a provider change is visible.

10. Run the consumer suite, the provider suite, lint, and format with spgr-run-tests and confirm clean before write. Write each test file and the pact file through spgr-write-file. Record any non-obvious contract design choice with spgr-log-decision. Commit one logical change per commit.

## Notes

- The output is source code verified by spgr-run-tests and CI rather than by an envelope schema. Verification is the provider replaying the pact and the can-i-deploy gate in CD, not a registered artifact schema.
- The contract coverage report, the dependency graph, and any spec-pact discrepancy record are written via spgr-write-artifact with a registered schema added in a later increment.
- Contract tests assert only interface shape. Business logic correctness belongs to unit and integration tests. Build only the interactions the consumer uses in production, not every permutation.
