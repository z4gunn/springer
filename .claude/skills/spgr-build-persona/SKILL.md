---
name: spgr-build-persona
description: Construct research-grounded user personas from UGC mining output, interview summaries, and review-platform data, where every attribute traces to a cited source. Use when the Discovery Agent must turn research inputs into evidence-backed personas before ICP selection, or when the PM Agent needs a concrete user model to anchor stories.
---

# build-persona

## Purpose

Produce a persona artifact that makes the target user concrete and shared across agents, with each characteristic grounded in research evidence. Invented personas are worse than none, so this skill enforces source tracing: every goal, pain point, behavior, current tool, and willingness-to-pay figure carries an evidence citation, and the confidence map reflects how many independent sources back each attribute. Read inputs with spgr-read-file or spgr-read-artifact, write the result with spgr-write-artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `research_notes` | Raw research notes, interview summaries, or synthesized findings |
| `ugc_mining_output` | Output from any `spgr-mine-*` skill invocation |
| `interview_summaries` | Optional structured interview summaries when user interviews were conducted |
| `product_context` | Short description of the product being built, used to decide which user attributes are most relevant |
| `persona_count` | Target number of distinct personas, defaulting to 1 to 3 by product complexity |

## Outputs

| Artifact | Description |
|----------|-------------|
| `personas` | Array of persona documents, one per distinct user role or market side |
| `evidence_map` | For each persona characteristic, the source data point or points that support it |
| `market_side` | Which side of the market each persona represents, for multi-sided products |
| `persona_relationships` | How the personas relate, for example independent users, buyer versus user, or collaborating roles |

Each persona document carries these fields: `persona_id`, `name`, `archetype_label`, `market_side`, `demographics` (`role`, `company_size`, `experience_level`), `goals` (each `goal` with an `evidence_source`), `pain_points` (each `pain` with `severity` and `evidence_source`), `current_solutions` (each `tool` with `frustration`), `behaviors` (each `behavior` with `context`), `willingness_to_pay` (`range` with `evidence_source`), and `key_quote`.

Each evidence citation carries `source_type` (one of `reddit`, `interview`, `review`, `ugc`), `source_url_or_ref`, and `quote_or_paraphrase`.

## Procedure

1. Read every research input. Aggregate the UGC findings with spgr-synthesize-painpoints so pain points arrive pre-clustered with their source signals.
2. Decide the persona set. For multi-sided markets (marketplace buyers and sellers, B2B buyers and end users), create a separate persona per side and do not collapse distinct roles into one. Set `market_side` on each, and record how the personas relate in `persona_relationships`.
3. For each persona, fill the schema fields from the inputs. Favor behaviors and current-workflow friction over demographics. A user's current workflow and its friction points are more useful for design than age or job title.
4. Cite every attribute. Attach an evidence citation to each goal, pain, current solution, behavior, and the willingness-to-pay range. Ground willingness-to-pay in pricing research and UGC signals, never invent it.
5. If a needed attribute cannot be sourced from the inputs and the gap is a context detail, call spgr-search-web to find demographic or behavioral context and cite the result. If the gap is core to the persona and unsourceable, mark that attribute `proposed` and flag it for validation rather than inventing it.
6. Set confidence per attribute. An attribute backed by one source is `proposed`. An attribute corroborated by two or more independent sources is `confirmed`. Build the artifact confidence map from these per-attribute settings.
7. Assemble the envelope with spgr-write-artifact and validate it inline with spgr-validate-artifact. Record the source-grounding rule and the persona-set decision with spgr-log-decision, then version with spgr-version-artifact.
8. If the research inputs are too thin to ground a persona at all, or a multi-sided market has no data for one side, stop and raise spgr-escalate with the precise list of missing inputs rather than producing an invented persona.
9. After the personas validate, hand off to spgr-build-icp to select which persona or personas the product prioritizes first.

## Notes

- Output type is an envelope artifact (persona document set). The `persona` content type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- No attribute is exempt from the citation rule. An attribute with no `evidence_source` fails the source-grounding check and must be marked `proposed` or removed.
- Confidence requires independent sources. Two quotes from the same thread or the same interview count as one source, not two.
