# Data-flow diagram versus activity diagram

A short note to keep two adjacent notations distinct. This skill models control and process flow. A data-flow diagram (DFD) is a different notation, available on request, that models data movement. Do not conflate them.

## What an activity diagram or flowchart shows
Control flow. The order of steps, the branches a process takes, the loops it repeats, the work it runs concurrently, and which actor performs each step. The arrows mean "then do this next." A decision picks one branch, a fork runs all branches. This is what the skill produces.

## What a DFD shows
Data movement. How data moves between processes, external entities, and data stores. The arrows mean "this data flows from here to there." A DFD has four element types: external entity, process (a transformation of data), data store, and data flow. It deliberately omits control flow. A DFD has no decision diamonds, no loops, no fork and join, and no sequencing of steps. A leveled DFD decomposes a process into a lower-level DFD, it does not branch on a condition.

## The distinction in one line
An activity diagram answers "in what order does the work happen, and who does it." A DFD answers "what data moves between which processes and stores." An arrow on an activity diagram is a control transition. An arrow on a DFD is a named data flow.

## When a request is really a DFD
If the request is about where data originates, what transforms it, and where it is stored, with no interest in branching, looping, or step order, it is a DFD, not an activity diagram. Producing an activity diagram for a data-movement question, or a DFD for a control-flow question, gives the reader the wrong model. Name the mismatch and confirm which notation the question needs before drawing.
