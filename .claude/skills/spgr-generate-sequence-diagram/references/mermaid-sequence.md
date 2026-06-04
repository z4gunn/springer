# Mermaid sequence cheat-sheet

Notation for `sequenceDiagram`, the default for this skill. Mermaid renders inline in GitHub and Obsidian with no toolchain. Escalate to PlantUML on the triggers in /Users/gunderer/Repos/springer/.claude/references/tool-selection.md.

## Participants

Declare each participant up front with a stable domain alias, so a later rename touches one line.

```
participant API as API Gateway
actor User
```

Use `actor` for a human or external system, `participant` for a service, component, or object.

## Message arrows

| Syntax | Meaning |
|--------|---------|
| `A->>B: msg` | synchronous call, solid filled arrowhead |
| `A-)B: msg` | asynchronous call, open arrowhead, caller does not block |
| `B-->>A: msg` | return, dashed line, open arrowhead |
| `A->>A: msg` | self-call |
| `A-xB: msg` | message with a lost or failed marker |

Reserve `-)` for genuinely non-blocking calls. A slow synchronous call is still `->>`.

## Activation bars

Two ways to draw the bar that shows a participant processing. Pick one per diagram and stay consistent.

- Suffix form, self-balancing: `A->>+B: call` opens the bar, `B-->>-A: return` closes it. The `+` and `-` pair on the arrows, so there is nothing to leave open.
- Explicit form: `activate B` ... `deactivate B`. Every `activate` needs a matching `deactivate`. Mermaid renders an `activate` with no `deactivate` to clean SVG with a bar that never closes, a silent failure. The lint in scripts/lint-sequence.sh catches it.

Do not mix an opening `+` suffix with a closing explicit `deactivate` for the same bar. The lint counts explicit keywords only, so a `+` open paired with a `deactivate` close reads as an unmatched `deactivate`. Open and close with the same style.

## Combined fragments

Each opener closes with `end`. Keep nesting shallow.

```
alt condition
  A->>B: path one
else other condition
  A->>B: path two
end

opt only when true
  A->>B: optional step
end

loop until done
  A->>B: repeated step
end

par run together
  A->>B: branch one
and
  A->>C: branch two
end
```

`critical` and `break` exist with the same `end` rule. Mermaid has no `ref`. When a scenario needs `ref`, escalate to PlantUML.

## Ordering and notes

- `autonumber` at the top numbers every message. Turn it on when call ordering is part of the deliverable.
- `Note over A,B: text`, `Note left of A: text`, and `Note right of A: text` annotate without adding a message.

## No communication diagram, use the numbered-flowchart approximation

Mermaid has no communication-diagram type. The communication view is the same interaction laid out by link topology rather than the time axis, with decimal-numbered messages (1, 1.1, 2) encoding order. Approximate it with a `flowchart` whose edge labels carry the sequence numbers.

```
flowchart LR
  User -->|"1: login"| Auth
  Auth -->|"1.1: persist"| Store
  Auth -->|"2: token"| User
```

State the chosen tool and the reason in the artifact, for example `Mermaid flowchart approximation of a communication view, Mermaid has no native communication diagram`. When the topology or the numbering needs real fidelity, escalate to PlantUML, which has a true communication and object form. See references/plantuml-sequence.md.

## Render

`npx @mermaid-js/mermaid-cli@11 -i <src>.mmd -o <src>.svg`. Use scripts/render-sequence.sh, which lints first and then renders.
