---
name: spgr-scaffold-transactional-email
description: Scaffold a project's transactional email system as source code, covering email-service-provider integration with injected credentials, an asynchronous send job, a template rendering pipeline, a non-production environment guard that routes mail to a catching inbox, unsubscribe and bounce hooks, a development-only preview route, and a CI snapshot test per template. Use when the Async Infrastructure agent stands up transactional email for a project, or when the Backend Developer agent needs the email foundation in place before wiring account confirmation, password reset, welcome, or billing-receipt emails.
---

# scaffold-transactional-email

## Purpose

Lay down the transactional email foundation so delivery is asynchronous, templates are testable, and mail can never be sent to real addresses from a non-production environment. Sending email inside a request handler couples user-facing latency and availability to the ESP, so this scaffold enqueues every send. A staging environment that delivers to real inboxes will eventually email a real customer, so the non-production environment guard is a required part of the output, not an option. The output is source code, not an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `email_requirements` | Which transactional emails the product sends (account confirmation, password reset, welcome, billing receipts, and so on) |
| `esp` | The email service provider to integrate (SendGrid, Postmark, Resend, SES, or equivalent) |
| `template_format` | The template system to scaffold (MJML, HTML, React Email, Handlebars) |
| `architecture_constraints` | The approved background-job or queue mechanism the send job must enqueue onto, from the architecture ADRs |

Read each input file with spgr-read-file. Read any upstream architecture or async-job artifact with spgr-read-artifact and validate it with spgr-validate-artifact before scaffolding against it.

## Outputs

| Artifact | Description |
|----------|-------------|
| ESP integration module | Provider client configured with credentials injected from environment, never inlined |
| Email send job | Asynchronous job that enqueues the send onto the approved queue, callable from request handlers without blocking |
| Template system | Template files in the chosen format plus a rendering pipeline with typed variable injection |
| Environment guard | Code path that forces every send in development and test to a catching inbox (Mailpit, Mailtrap) or preview mode, with real delivery reachable only in production |
| Unsubscribe and bounce hooks | Routes and handlers for unsubscribe and ESP bounce or complaint webhooks, sized to CAN-SPAM and GDPR |
| Preview route | Development-only route that renders a template with sample variables in a browser without sending |
| Template snapshot tests | One CI test per template that renders with expected variables, asserts valid HTML, and fails on unexpected output change |

Write every file with spgr-write-file.

## Procedure

1. Confirm the inputs are complete and consistent. If the ESP, the template format, or the approved queue mechanism is missing or contradicts the architecture constraints, stop and raise spgr-escalate with the precise list of what is missing. Do not pick an ESP or a queue by default.

2. Scaffold the ESP integration module. Read credentials from environment variables and document the required keys in `.env.example`. Never commit a real key.

3. Scaffold the asynchronous send job. The job enqueues the send onto the approved queue from the architecture constraints. Request handlers call the enqueue path only. No request handler sends synchronously through the ESP.

4. Scaffold the template system in the chosen format, with a rendering pipeline that injects typed variables and one template file per email in `email_requirements`.

5. Scaffold the non-production environment guard. In development and test, every send routes to the catching inbox or preview mode. Real delivery is reachable only when the environment is production. This guard is non-negotiable. If the architecture offers no safe non-production destination, escalate rather than ship without the guard.

6. Scaffold the unsubscribe and bounce handling. Add an unsubscribe route and a webhook handler for ESP bounce and complaint events. Strictly transactional mail (password reset, receipts) is exempt from the unsubscribe link, but the infrastructure must be present for any email that is not strictly transactional. Tag spgr-tag-vertical-agent for compliance review when the email set includes non-transactional content.

7. Scaffold the development-only preview route that renders any template with sample variables in a browser and never sends. Guard the route so it is unreachable in production.

8. Write the template snapshot tests test-first, one per template. Each test renders the template with its expected variables, asserts the output is valid HTML, and compares against a committed snapshot so an unexpected change fails CI. Confirm the suite fails before the templates exist, then passes once they do, and run it with spgr-run-tests.

9. Lint and format the scaffold clean before handing off. For TypeScript or JavaScript, conform to `.claude/references/typescript-standards.md` and pass `tsc --noEmit`. Keep the work to one logical change per commit. Record any consequential choice (ESP client options, queue binding, guard mechanism) with spgr-log-decision.

## Notes

- The output is source code verified by spgr-run-tests and CI, not by an envelope schema. There is no registered artifact type for this scaffold.
- Build only the emails listed in `email_requirements`. Do not scaffold templates, hooks, or routes for emails the product does not send.
- The environment guard and the asynchronous send job are the two correctness properties of this scaffold. A reviewer rejects the output if either is missing.
- Reference any consumed artifact's fields through spgr-validate-artifact against the schema registry at `schemas/` rather than restating field lists here.
