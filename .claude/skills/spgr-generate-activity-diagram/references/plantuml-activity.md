# PlantUML activity (beta) cheat sheet

The escalation notation for an activity diagram. Use the new beta syntax (the form below), not the legacy `(*)` syntax. Reach for PlantUML when the process needs true swimlanes by responsibility or formal fork and join concurrency, the two features Mermaid flowchart cannot express. Swimlane and fork layouts need Graphviz, confirm with `dot -V`.

## Contents
- Skeleton
- Actions and object flow
- Decision and merge
- Loops
- Fork and join
- Swimlanes
- Decision versus fork
- Worked examples

## Skeleton
Every diagram opens `@startuml`, begins flow at `start`, and ends at `stop` (a final node) or `end` (a flow-final node). Close with `@enduml`. Comment lines begin with a single quote.

```
@startuml
start
:First action;
stop
@enduml
```

## Actions and object flow
- `:text;` is an action node. The trailing semicolon is required.
- `:text|` and other terminators set a different node style, the semicolon form is the default.
- Show object flow, where an arrow carries a data object rather than pure control, with an explicit note or an action named for the object, for example `:Order record;`. Reserve this for the case where the object passed matters to the reader.

## Decision and merge
Use `if/then/elseif/else/endif`. Put a guard in the `if (...)` and label each branch outcome in `then (...)` and `else (...)`. The `endif` is the merge. Always close with an `else` so the guard set is exhaustive. The lint flags any `if` block that reaches `endif` with no `else`.

```
if (Approved?) then (yes)
  :Issue purchase order;
else (else)
  :Receive rejection notice;
endif
```

Add intermediate cases with `elseif (cond) then (label)` before the final `else`.

## Loops
- `repeat` ... `repeat while (cond)` is a do-while loop, the body runs at least once.
- `while (cond)` ... `endwhile` is a pre-test loop, the body may run zero times.

```
repeat
  :Process item;
repeat while (More items?)
```

## Fork and join
Model true concurrency with `fork`, one or more `fork again`, and `end fork`. Every branch between the opener and `end fork` runs concurrently, and `end fork` is the join that synchronizes them before the flow continues. The lint flags a `fork` with no matching `end fork`.

```
fork
  :Reserve inventory;
fork again
  :Authorize payment;
fork again
  :Send order-received email;
end fork
:Confirm order;
```

## Swimlanes
Declare a swimlane with `|Lane Name|`. Every action after a lane declaration belongs to that lane until the next declaration. Declare the first lane before `start` so the start node lands in a named lane, otherwise the render fails. Use swimlanes only when more than one actor participates. A single-actor process needs no lanes, use a Mermaid flowchart instead.

```
|Customer|
start
:Submit request;
|Manager|
:Review request;
```

## Decision versus fork
A decision is a diamond that selects exactly one guarded branch. A fork is a bar that runs all branches concurrently and joins them. The glyph change is a semantic change. Do not use `if/else` to express concurrency, and do not use `fork` to express a choice. Pair every decision with its `endif` merge and every `fork` with its `end fork` join.

## Worked examples
The swimlane-activity and forkjoin-concurrent golden templates in assets/ are the canonical references. The swimlane example covers multi-actor responsibility with a branch. The fork-join example covers concurrency with a join followed by a decision.
