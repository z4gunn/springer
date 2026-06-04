# Mermaid stateDiagram-v2 notation

Notation cheat-sheet for authoring an entity lifecycle in Mermaid stateDiagram-v2, the default renderer for a state diagram. Shared family rules (render-and-validate commands, quality rules, boundaries) live in /Users/gunderer/Repos/springer/.claude/references/diagram-standards.md. The Mermaid-vs-PlantUML decision table and the full Mermaid limitation list live in /Users/gunderer/Repos/springer/.claude/references/tool-selection.md. This file adds only the state-diagram syntax.

## Contents
- Core syntax
- Transition labels
- Composite and branching
- What Mermaid drops

## Core syntax
- Declare the diagram with `stateDiagram-v2` on its own line.
- `[*] --> First` is the initial pseudostate. `Last --> [*]` is a final state. Use exactly one initial pseudostate per region.
- A bare state name declares a state. `state "Display label" as s1` gives a state an id distinct from its label.
- A transition is `src --> dst`. Add a label after a colon: `src --> dst: label`.

## Transition labels
- Write every label in canonical form `trigger[guard]/action`. Each part is optional, but keep the order.
  - trigger: the event that fires the transition, for example `submit`.
  - `[guard]`: a boolean condition that must hold, for example `[itemsPresent]`.
  - `/action`: the effect run on the transition, for example `/reserveStock`.
- A guard with no trigger is a completion transition: `Decision --> Approved: [score > 80]`.
- Prefer one named trigger per event across the diagram so the lint can tell which events are handled.

## Composite and branching
- A composite state nests substates:
  ```
  state Active {
      [*] --> Running
      Running --> Paused: pause
  }
  ```
  Give the composite its own initial pseudostate.
- Branching pseudostates: `state Choice <<choice>>`, `state Fork <<fork>>`, `state Join <<join>>`.
- A `<<choice>>` must be guard-exhaustive. Cover every condition, including a final `[else]` or an unguarded default branch, or the lint flags a fall-through.
- Concurrency uses `--` inside a composite to split regions. Treat this as a Mermaid-fragile feature, see below.

## What Mermaid drops
stateDiagram-v2 silently drops four feature families, leaving a clean render with missing semantics:
- history pseudostates `[H]` (shallow) and `[H*]` (deep)
- `entry/`, `exit/`, and `do/` behaviors
- internal transitions (a `trigger/action` line inside a state that does not leave it)
- orthogonal (concurrent) regions

Run `scripts/select-renderer.py` on the draft. If it reports any of these, author the model in PlantUML instead and let the script stamp the reason. See [plantuml-state.md](plantuml-state.md).
