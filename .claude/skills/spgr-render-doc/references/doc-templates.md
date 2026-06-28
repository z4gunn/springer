# doc-templates

The path map and per-type Markdown layouts for spgr-render-doc. Read the entry for an artifact type before rendering it.

## Contents

- [Conventions](#conventions)
- [Path map](#path-map)
- [Confidence markers](#confidence-markers)
- [Discovery types](#discovery-types)
- [Product types](#product-types)
- [Architecture types](#architecture-types)
- [Design types](#design-types)
- [docs/README.md index](#docsreadmemd-index)

## Conventions

- Every doc opens with an H1 title, then a one-line provenance note: the source `artifact_id`, `version`, and `producing_agent`, and the line `Generated from the typed artifact in runs/<run-id>/artifacts/. The artifact is the source of truth. Do not hand-edit this file, regenerate it.`
- Reformat content fields into prose, tables, and lists. Do not add analysis that is not in the artifact. Do not drop evidence references, rationale, or open questions.
- Use plain Markdown only. No HTML. No em-dashes, semicolons, body-text bold, italics, or emojis in generated prose, matching the repository authoring voice.

## Path map

| artifact_type | Phase | Output path |
|---------------|-------|-------------|
| `icp` | Discovery | `docs/discovery/icp.md` |
| `competitive-matrix` | Discovery | `docs/discovery/competitive-matrix.md` |
| `market-sizing` | Discovery | `docs/discovery/market-sizing.md` |
| `discovery-synthesis` | Discovery | `docs/discovery/discovery-synthesis.md` |
| `go-no-go` | Discovery | `docs/discovery/go-no-go.md` |
| `prd` | Product | `docs/product/prd.md` |
| `nfr` | Product | `docs/product/nfr.md` |
| `risk-register` | Product | `docs/product/risk-register.md` |
| `definition-of-done` | Product | `docs/product/definition-of-done.md` |
| `user-story` + `acceptance-criteria` | Product | `docs/product/user-stories.md` (rolled up, one section per story) |
| `architecture-options` | Architecture | `docs/architecture/architecture-options.md` |
| `adr` | Architecture | `docs/architecture/adr/ADR-NNN.md` plus `docs/architecture/adr/index.md` |
| `api-spec` | Architecture | `docs/architecture/api-spec.md` |
| `data-dictionary` | Architecture | `docs/architecture/data-dictionary.md` |
| `erd` | Architecture | `docs/architecture/erd.md` plus `docs/architecture/diagrams/erd.mmd` |
| `system-diagram` | Architecture | `docs/architecture/system-diagram.md` plus `docs/architecture/diagrams/system-diagram.mmd` |
| `infrastructure-diagram` | Architecture | `docs/architecture/infrastructure-diagram.md` plus `docs/architecture/diagrams/infrastructure-diagram.mmd` |
| `design-directions` | Design | `docs/design/directions.md` |

A type not in this map is rendered to `docs/<phase>/<artifact_type>.md` when the phase is known, otherwise it is skipped and noted in `render_report`.

## Confidence markers

Render a marker at the head of every section that has a `confidence_map` entry, on its own line directly under the section heading:

- `confirmed` -> `Status: confirmed`
- `proposed` -> `Status: proposed (awaiting human review)`
- `needs-human-input` -> `Status: NEEDS HUMAN INPUT` followed by a short line naming what is missing if the artifact states it.

When the artifact as a whole carries `needs-human-input`, add a callout block at the top of the doc, right after the provenance note, listing every section that needs input, so the human sees the open items first.

## Discovery types

- `icp`: H2 sections for the target customer, firmographic or demographic attributes, behavioral attributes, buying signals, willingness to pay, exclusion criteria, and prioritization rationale. Render attribute sets as tables.
- `competitive-matrix`: a table with one row per competitor and columns for the compared dimensions, then a short positioning summary below.
- `market-sizing`: TAM, SAM, and SOM as a short table with the estimate and the stated assumptions per row.
- `discovery-synthesis`: ranked pain-point clusters as H2 sections, each with the cluster name, the evidence quotes, and the source references the artifact carries.
- `go-no-go`: the recommendation up top as a single clear line, then the supporting rationale and the evidence references.

## Product types

- `prd`: H2 sections for problem statement (with its evidence references), goals (a table of goal, success metric, measurement method), personas, in-scope features (feature and rationale), out-of-scope items (item and reason excluded), success metrics, and open questions (a table of question, owner, deadline). The out-of-scope list is as deliberate as the scope list, render it in full.
- `nfr`: one H2 per NFR category, each with the requirement and its target and measurement.
- `risk-register`: a table with one row per risk, columns for risk, likelihood, impact, and mitigation.
- `definition-of-done`: the DoD checklist rendered as a Markdown checkbox list.
- rolled-up `user-stories.md`: one H2 per story titled `STORY-ID: title`, with the As a / I want / So that lines, the persona and PRD-goal references, the estimated size, and the INVEST result (note any failed letters and the split recommendation if present). Directly under each story, render its acceptance criteria as an H3 `Acceptance criteria` with each scenario in Given / When / Then form labeled by scenario type, and a one-line coverage summary.

## Architecture types

- `architecture-options`: this doc drives the human selection gate, so lead with a comparison table, one column per option, rows for topology, data model, API style, auth model, infrastructure, and the tradeoff profile fields (initial complexity, scalability ceiling, reversibility cost, monthly cost at scale, required expertise). Below the table, an H2 per option with its strengths and weaknesses. Then the scoring matrix as a table. End with a clear note that the human selects the option and the agent does not.
- `adr`: H1 `ADR-NNN: title`, then a `Status:` line, then H2 sections Context, Decision, and Consequences. Render consequences as three labeled lists: positive, negative, neutral. If the ADR supersedes or is superseded by another, link it by ADR number. Rebuild `docs/architecture/adr/index.md` as a table of every ADR file in the directory: number, title, status, link.
- `api-spec`: group endpoints by resource, one H2 per resource, a table of method, path, and summary per endpoint. Keep it a readable overview, the typed artifact remains authoritative for the full contract.
- `data-dictionary`: one H2 per entity, a table of field, type, constraints, and PII marker.
- `erd`, `system-diagram`, `infrastructure-diagram`: H1 title, a one-paragraph description if the artifact has one, then the Mermaid inside a fenced ```mermaid block. Below the diagram, add a line linking the `.excalidraw` and `.png` copies when they were produced. Always write the raw Mermaid to `docs/architecture/diagrams/<name>.mmd` as the source for the excalidraw render.

## Design types

- `design-directions`: one H2 per direction, each with visual language, interaction model, information-architecture rationale, emotional tone, the key screen mockups described, and the per-persona usability prediction. At the top, link `docs/design/index.html` so the human opens the clickable mockups produced by spgr-render-design-mockups. Mark the whole doc `needs-human-input` until a direction is selected.

## docs/README.md index

Rebuild `docs/README.md` on each run as a navigable index:

- H1 `Project documentation`, a one-line note that these are regenerable human-readable copies of the typed artifacts in `runs/`, which remain the source of truth.
- One H2 per phase present (Discovery, Product, Architecture, Design), each a bullet list linking every doc in that phase by its title.
- Preserve links to docs from phases rendered in earlier runs, do not drop them when rendering a single phase.
