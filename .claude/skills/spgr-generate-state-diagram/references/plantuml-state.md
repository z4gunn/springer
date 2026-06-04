# PlantUML state notation

Notation cheat-sheet for authoring an entity lifecycle in PlantUML state, the escalation renderer when the model needs a feature Mermaid stateDiagram-v2 drops. Shared family rules (render-and-validate commands, quality rules, boundaries) live in /Users/gunderer/Repos/springer/.claude/references/diagram-standards.md. The Mermaid-vs-PlantUML decision table and the Mermaid limitation list live in /Users/gunderer/Repos/springer/.claude/references/tool-selection.md. PlantUML composite state layout needs Graphviz, confirmed with `dot -V`. This file adds only the state-diagram syntax.

## Contents
- When to use this renderer
- Core syntax
- The four escalation features
- Recording the escalation reason

## When to use this renderer
Escalate to PlantUML when the model uses any of: history pseudostates, entry/exit/do behaviors, internal transitions, or orthogonal regions. Mermaid drops all four silently. Run `scripts/select-renderer.py --stamp <draft>` to confirm the trigger and record it in the source before authoring.

## Core syntax
- Wrap the diagram in `@startuml` and `@enduml`.
- `[*] --> First` is the initial pseudostate. `Last --> [*]` is a final state. One initial pseudostate per region.
- A transition is `src --> dst : label`. Write the label in canonical form `trigger[guard]/action`.
- A composite state nests substates:
  ```
  state Active {
      [*] --> Current
      Current --> Paused : pause
  }
  ```

## The four escalation features
- History: `Active[H]` shallow history, `Active[H*]` deep history. Use `Paused --> Active[H] : resume` so re-entry resumes the prior substate. Reserve history for genuine resume-after-interrupt cases. Prefer an explicit initial substate otherwise.
- Behaviors: attach durable behavior to a state rather than duplicating an action on every inbound transition.
  ```
  Trial : entry / startTrialClock
  Trial : do / sendNurtureEmail
  Trial : exit / stopTrialClock
  ```
- Internal transition: a `trigger / action` line on a state that handles an event without leaving the state, so no entry or exit fires: `Trial : reminder / logReminder`.
- Orthogonal regions: split a composite into concurrent regions with a `--` separator line, each region with its own initial pseudostate:
  ```
  state Active {
      state Billing { [*] --> Current }
      --
      state Usage { [*] --> Within }
  }
  ```

## Recording the escalation reason
Keep the escalation reason as a header comment in the `.puml` source so the choice is traceable in the diff. A PlantUML comment starts with a single quote:
```
' escalation-reason: PlantUML required, Mermaid stateDiagram-v2 would silently drop: shallow or deep history pseudostate
```
`scripts/select-renderer.py --stamp` writes this line. See the golden composite-with-history template in `assets/subscription-lifecycle.puml`.
