---
name: spgr-render-doc
description: Render one or more confirmed typed artifacts from the run store into human-readable Markdown under a project docs/ folder, carrying confidence signals through, embedding Mermaid diagrams, and producing a best-effort excalidraw and PNG copy of each diagram. Use when an early-phase agent (Discovery, Product Manager, Architect, Design) has written artifacts to runs/<run-id>/artifacts/ and the human needs a readable review copy to drive a human-in-the-loop checkpoint, or when an artifact changes and its docs copy must be regenerated.
---

# render-doc

## Purpose

The early-phase agents write everything as typed JSON envelope artifacts in `runs/<run-id>/artifacts/`. Those are agent-to-agent handoff contracts, not something a human reviews comfortably at a checkpoint. This skill is presentation and rendering only. It reads confirmed artifacts and reformats their content into developer-facing Markdown under `docs/`, so the human reads readable docs at the architecture-approval and design-selection gates instead of JSON. The typed artifact in the run store stays the single source of truth. The doc is a regenerable copy, the same posture as spgr-render-diagram-excalidraw. This skill authors no new content and owns no model. When an artifact changes, regenerate the doc from the artifact rather than hand-editing the doc.

## Inputs

| Field | Description |
|-------|-------------|
| `artifact_ids` | One or more artifact ids to render. A `user-story` plus its `acceptance-criteria` artifacts are rolled into one document, so pass them together. |
| `run_id` | The run whose store holds the artifacts, for example `dryrun`. Artifacts are read from `runs/<run-id>/artifacts/`. |
| `docs_path` | Optional. The docs root, default `docs/`. The skill writes under `docs/<phase>/`. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Markdown docs | Human-readable `.md` files under `docs/<phase>/`, one per artifact (or one rolled-up file for stories), with confidence markers carried through. See the path map in [references/doc-templates.md](references/doc-templates.md). |
| Diagram sources | For each diagram artifact, the extracted Mermaid written to `docs/architecture/diagrams/<name>.mmd`, plus a best-effort `<name>.excalidraw` and `<name>.png` beside it. |
| `docs/README.md` | An index linking every generated doc, grouped by phase, kept current on each run. |
| `render_report` | A list of the paths written and any artifact that was skipped because it failed validation. |

## Procedure

1. For each artifact id, read it with spgr-read-artifact from `runs/<run-id>/artifacts/`. Validation runs first. If an artifact fails validation or carries an unresolved schema-version mismatch, do not render it. Record it in `render_report` as skipped with the validation error, and continue with the rest. A doc must never present an artifact the run store could not confirm is well-formed.

2. Resolve the phase and target path from the artifact's `artifact_type` using the path map in [references/doc-templates.md](references/doc-templates.md). Create parent directories through spgr-write-file with `create_parents` true. Read that reference for the per-type section layout before rendering a type you have not rendered this session.

3. Render the artifact content into the type's Markdown template. Reformat the content fields into readable prose, tables, and lists. Do not invent, summarize away, or add content that is not in the artifact. Where the artifact carries evidence references, rationale, or open questions, keep them, because they are what the human weighs at the checkpoint.

4. Carry confidence through. For every section that has an entry in the artifact `confidence_map`, render a visible marker at the section head: `confirmed`, `proposed`, or `needs-human-input`. A `needs-human-input` section is the human's action item, so make it unmissable. See the marker convention in [references/doc-templates.md](references/doc-templates.md).

5. For a diagram artifact (`erd`, `system-diagram`, `infrastructure-diagram`), embed the Mermaid inside a fenced ```mermaid block in the Markdown so it renders in GitHub and Obsidian, and also write the raw Mermaid to `docs/architecture/diagrams/<name>.mmd`. Then attempt the polished copy: invoke spgr-render-diagram-excalidraw on that `.mmd` source to produce `<name>.excalidraw` and `<name>.png` beside it. This step is best-effort. If the optional `~/.claude/skills/excalidraw-diagram/` dependency is absent or the render fails, skip it, keep the embedded Mermaid, and note the skip in `render_report`. Never fail the doc render because the excalidraw copy could not be produced.

6. For `adr` artifacts, write one file per ADR at `docs/architecture/adr/ADR-NNN.md` and rebuild `docs/architecture/adr/index.md` listing every ADR file present in that directory with its number, title, and status. For the rolled-up stories doc, write one section per `user-story`, each followed by its linked `acceptance-criteria` scenarios in Given/When/Then form.

7. Update `docs/README.md` so it links every doc that exists under `docs/`, grouped by phase (Discovery, Product, Architecture, Design), so the folder is navigable. Add new links, do not drop links to docs from other phases that already exist.

8. Write every file with spgr-write-file in overwrite mode, since docs are regenerable copies. Confirm each path stays under the repository root, the write-file boundary already enforces this. Return `render_report` with the paths written and anything skipped.

## Notes

- Docs are not typed artifacts. They carry no envelope, no checksum, and no schema, the same as the excalidraw render outputs and the spgr-generate-api-docs Markdown. Do not route them through spgr-write-artifact or spgr-validate-artifact.
- This skill never writes into `runs/`. It only reads the artifact store and writes under `docs/`. The run store is the source of truth and stays unchanged.
- This skill has no Phase 1 vault spec. It was authored to the Springer build standards as a net-new capability, so there is no "Phase 2 Build Notes" brief to map from.
- Do not render an artifact whose top-level intent is still `needs-human-input` as if it were settled. Render it with the marker so the gap is visible, which is the point of generating the doc early.
- The per-type templates and the full path map live in [references/doc-templates.md](references/doc-templates.md). Read it rather than guessing a layout for a type.
