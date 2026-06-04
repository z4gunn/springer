# Mermaid flowchart cheat sheet

The default notation for an activity diagram. Renders inline in GitHub and Obsidian with no toolchain. Use it for a single sequential or lightly branching process with one actor. Escalate to PlantUML activity for true swimlanes or formal fork and join, per the tool-selection table.

## Contents
- Header and direction
- Node shapes
- Edges and guards
- Decision and merge
- Loops
- What Mermaid flowchart cannot do
- Worked example

## Header and direction
Open with `flowchart` and a direction: `TD` top-down, `LR` left-right. Top-down reads as a process from start to end. Left-right suits a wide pipeline.

```
flowchart TD
```

## Node shapes
Map each shape to its activity-diagram role.

| Syntax | Shape | Role |
|--------|-------|------|
| `id([text])` | stadium | start and end node |
| `id[text]` | rectangle | action or process step |
| `id{text}` | diamond | decision |
| `id[/text/]` | parallelogram | input or output, an object passed in or out |
| `id((text))` | circle | connector or merge point when an explicit node helps |

A node id is declared once. Reuse the id to draw more edges to or from the same node.

## Edges and guards
- `a --> b` is control flow from a to b.
- `a -->|guard| b` labels the edge with a guard condition. Use a guard on every outgoing edge of a decision.
- `a -.-> b` is a dashed edge, reserve it for a non-primary or fallback path when the distinction aids reading.

## Decision and merge
A decision is a diamond with one outgoing edge per guarded branch. The branches pick exactly one path. Make the guard set mutually exclusive and exhaustive, and always include an `else` edge so no input falls through unhandled. Bring the branches back together at a shared downstream node, which is the merge.

```
check{All fields valid?}
check -->|yes| persist[Save record]
check -->|else| reject[Return errors]
persist --> done([End])
reject --> done
```

A decision is not a fork. A decision selects one branch. A fork runs all branches concurrently and Mermaid flowchart has no fork primitive. When the process needs concurrency, escalate to PlantUML activity.

## Loops
A loop is an edge back to an earlier node, usually gated by a decision so it can terminate.

```
attempt[Try operation] --> ok{Succeeded?}
ok -->|yes| done([End])
ok -->|else| attempt
```

## What Mermaid flowchart cannot do
- No fork and join concurrency primitive. Approximate with parallel edges only when timing is not modeled, otherwise escalate.
- `subgraph` groups nodes but does not partition by responsibility. It is not a swimlane. For responsibility by actor, escalate to PlantUML activity swimlanes.
- No object-flow node distinct from control flow beyond the parallelogram convention above.

See the full limitation list in /Users/gunderer/Repos/springer/.claude/references/tool-selection.md.

## Worked example
A single-actor form submission with one branch. This is the simple-flowchart golden template.

```
flowchart TD
    start([Start]) --> validate[Validate submitted form]
    validate --> check{All fields valid?}
    check -->|yes| persist[Save record]
    check -->|else| reject[Return validation errors]
    persist --> notify[Send confirmation]
    notify --> done([End])
    reject --> done
```
