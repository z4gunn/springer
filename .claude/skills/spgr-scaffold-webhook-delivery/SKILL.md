---
name: spgr-scaffold-webhook-delivery
description: Scaffold the outbound webhook delivery system as source code, covering event fan-out, asynchronous HMAC-signed HTTPS delivery with exponential-backoff retry, a per-delivery log, and replay of a single event to a single endpoint. Use when the Async Infrastructure agent needs to implement outbound webhooks from a confirmed event taxonomy and endpoint registration model, or when the QA or developer agent needs the delivery system built test-first against its acceptance criteria before review.
---

# scaffold-webhook-delivery

## Purpose

Implement the outbound webhook delivery system so the product can notify external systems when domain events occur. A correct implementation is more than an HTTP request: delivery is asynchronous, retried with exponential backoff, signed so receivers can verify authenticity, logged so support can debug a missed delivery, and replayable so a customer whose endpoint was down can re-receive an event. This skill produces that scaffold as source code in the project under the approved architecture and async-infrastructure pattern, built test-first.

## Inputs

| Field | Description |
|-------|-------------|
| `event_taxonomy` | The set of domain events customers can subscribe to. Read upstream via spgr-read-artifact when it is an artifact, or via spgr-read-file when it is a source definition. |
| `endpoint_registration_model` | How customers register endpoint URLs (table, fields, per-endpoint enable flag). |
| `signing_key_strategy` | Per-endpoint signing keys or shared project keys. Drives where the secret is stored and looked up. |
| `acceptance_criteria` | Confirmed Given/When/Then set for the delivery stories, from spgr-write-acceptance-criteria. The build target. |
| `architecture_constraints` | The approved ADR queue and async-infrastructure pattern (queue or job runner) the scaffold must conform to. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Event dispatch | Fan-out from a domain event to every enabled subscribed endpoint, enqueuing one delivery job per endpoint. |
| Delivery job | Asynchronous worker that POSTs the signed payload to the customer endpoint with a request timeout and the retry policy. |
| Signing implementation | HMAC-SHA256 over the serialized payload plus timestamp, emitted as the `X-Signature-256` header with a timestamp header. |
| Delivery log | One record per attempt: endpoint URL, event type, payload hash, status code, attempt number, request and response timestamps. |
| Replay path | Re-deliver one logged event to one endpoint on demand, reusing the delivery job. |
| Test suite | Failing-first tests that cover dispatch fan-out, signing, retry, dedup, the log, and replay, run via spgr-run-tests. |

## Procedure

1. Read the inputs. Pull the event taxonomy, endpoint registration model, and signing-key strategy via spgr-read-artifact or spgr-read-file. Pull the confirmed acceptance criteria and the async-infrastructure ADR constraints. If the taxonomy, the registration model, or the signing-key strategy is missing or contradictory, or the architecture pins no async pattern, stop and raise spgr-escalate with the precise list of what is missing. Do not assume a queue technology or a key strategy.

2. Write the failing tests first. From the acceptance criteria, write tests before any implementation: dispatch enqueues one job per enabled endpoint, the signature verifies against the exact bytes sent, a 5xx or timeout triggers a retry, the retry stops at the max-attempts cap, a duplicate event id does not double-deliver, every attempt writes a log record, and replay re-sends one event to one endpoint. Confirm the suite fails via spgr-run-tests before implementing.

3. Implement dispatch as enqueue only. The domain event enqueues a delivery job per subscribed endpoint on the approved async runner. Never send the HTTP request inside the request and response cycle.

4. Implement signing on the serialized bytes. Serialize the payload once, compute HMAC-SHA256 over the serialized bytes and the timestamp using the key from the configured strategy, set `X-Signature-256` and the timestamp header, then send the exact same serialized bytes. Any change between signing and sending, including key reordering, invalidates the signature, so sign then send the same buffer.

5. Implement retry and failure handling. Apply exponential backoff with a max-attempts cap (default 5 attempts over 24 hours, adjust only to a value the acceptance criteria or NFRs state). On final failure, record the terminal state and trigger failure notification per the registration model.

6. Implement dedup. Carry a stable event id so a retry that lands after the first delivery already succeeded does not double-deliver. Make the delivery idempotent on that id.

7. Implement the delivery log and replay. Write one record per attempt with the fields in Outputs. Implement replay as a path that loads one logged event and re-runs the delivery job against one endpoint, reusing the same signing and retry code so a stale or duplicated implementation does not drift.

8. Lint, format, and verify. Run the linter and formatter to clean before commit. For TypeScript or JavaScript, conform to `.claude/references/typescript-standards.md` and pass `tsc --noEmit`. Run spgr-run-tests until the suite passes. Build only what the acceptance criteria require. Log the consequential choices (key strategy, backoff schedule, max attempts) via spgr-log-decision.

9. Escalate on a vertical conflict. If signing or replay touches a security or compliance constraint the inputs do not settle, tag the specialist via spgr-tag-vertical-agent before finalizing rather than deciding it here.

## Notes

- The output is source code, verified by spgr-run-tests and CI rather than by an envelope schema.
- Keep one logical change per commit and the working tree lint-clean and format-clean before each commit.
- Sign the serialized payload, then transmit that same serialized payload. Re-serialization between sign and send is the most common signature-mismatch defect.
- Replay must reuse the delivery job and signing code, not a parallel copy, so behavior stays identical to first delivery.
