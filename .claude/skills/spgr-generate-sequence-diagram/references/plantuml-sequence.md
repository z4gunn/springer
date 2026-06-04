# PlantUML sequence cheat-sheet

Notation for the PlantUML sequence diagram, the escalation target for this skill. PlantUML has no native GitHub or Obsidian render, so it needs Java or a server or a CI render step. Escalate from Mermaid only on the triggers in /Users/gunderer/Repos/springer/.claude/references/tool-selection.md: richer fragments, a true communication or object view, `autoactivate`, object creation, or finer styling Mermaid cannot express. State the trigger in the artifact when you escalate.

## Participants

```
participant "Order Service" as Service
actor User
```

## Message arrows

| Syntax | Meaning |
|--------|---------|
| `A -> B : msg` | synchronous call, solid filled arrowhead |
| `A ->> B : msg` | asynchronous call, open arrowhead |
| `A --> B : msg` | return, dashed line |
| `A ->x B : msg` | message with a lost marker |

## Activation bars

Three options. Pick one per diagram.

- `autoactivate on` at the top draws and balances every bar from the call and return arrows. There is no manual keyword to leave unbalanced. Prefer this for a request-response chain.
- Explicit `activate B` ... `deactivate B`. Every `activate` needs a matching `deactivate`. The lint in scripts/lint-sequence.sh counts these.
- The `++` and `--` arrow suffix, the same idea as Mermaid's `+`/`-`.

## Combined fragments

Each opener closes with `end`. PlantUML carries a broader set than Mermaid: `alt`/`else`, `opt`, `loop`, `par`/`and`, `critical`, `break`, `group`, and `ref over A, B : reused interaction`. A fragment left open is swallowed by `@enduml` and renders a misleading diagram with exit 0, so the lint is the structural gate, not the renderer.

```
alt condition
  A -> B : path one
else other condition
  A -> B : path two
end

ref over A, B : see the auth subflow diagram
```

## Object creation and destruction

```
create Order
A -> Order : new()
destroy Order
```

Mermaid approximates creation with `create participant` but has no destruction marker. This is a PlantUML escalation trigger.

## Communication and object form

PlantUML expresses both views that Mermaid cannot.

- Communication view: the same interaction by link topology, with `autonumber` driving decimal message numbers (1, 1.1, 2). Use it when the deliverable emphasizes who links to whom rather than the time axis.
- Object view: an instance-level layout using the `object` keyword, distinct from the class view.

```
@startuml
autonumber "1.1"
participant User
participant Auth
participant Store
User -> Auth : login
Auth -> Store : persist
Auth -> User : token
@enduml
```

When the request is a communication view and Mermaid is the default, either escalate here or use the Mermaid numbered-flowchart approximation in references/mermaid-sequence.md, and record the chosen tool and reason in the artifact. Mermaid has no native communication-diagram type.

## Styling

`skinparam` controls colors, fonts, and spacing beyond what Mermaid exposes. Reach for it only when a house style requires it, not as a default.

## Render

`java -jar ~/.plantuml/plantuml.jar -tsvg <src>.puml` writes `<src>.svg`. Class, composite-state, and swimlane layouts need Graphviz `dot`, which the sequence form does not. Use scripts/render-sequence.sh, which adds `-failfast2` so a parse error exits non-zero and checks the SVG for an embedded Syntax Error annotation.
