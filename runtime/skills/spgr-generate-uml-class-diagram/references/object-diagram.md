# Object diagram

How to build an object diagram: a concrete runtime snapshot used to validate a class model against one consistent case. Notation glyphs live in plantuml-syntax.md. Family quality rules and the render loop live in the shared standards at .claude/references/diagram-standards.md.

## What an object diagram is

An object diagram shows instance specifications, not types. Each box is one named instance of a class, with concrete slot values, linked to other instances. It captures one consistent moment in time. Use it to validate a class diagram against a real scenario or test fixture, to confirm the multiplicities and relationships hold for an actual case.

## Notation is PlantUML only

Mermaid has no object-diagram type. A runtime snapshot must use the PlantUML `object` keyword. Do not approximate an object diagram with a Mermaid class diagram, because that mixes instance-level and type-level content. When the request is for an object diagram, route to PlantUML with no exception.

## Rules that distinguish it from a class diagram

- Instances, not types. The box is `name : Type`, for example `order42 : Order`.
- Concrete slot values, not member declarations. `quantity = 2`, not `quantity : Int`.
- No multiplicity on links. Multiplicity is a type-level constraint. An object diagram shows the actual links that exist in this snapshot, so each link is a single concrete connection.
- No operations. Operations are behavior, which an instance snapshot does not depict.
- A link carries only a role label when one clarifies, for example `order42 --> alex : placedBy`.

## Snapshot consistency

The diagram must be a true snapshot: every slot value and every link must be mutually consistent for one moment. Do not show a half-applied state where one object reflects a change and a linked object does not. If the scenario spans a state change, draw two snapshots, one before and one after, not one mixed picture.

## Pair it with its class diagram

An object diagram is most useful next to the class diagram it instantiates. The pairing validates the class model: every instance must be an instance of a class in the model, every slot must map to a declared attribute, and every link must satisfy a declared association and its multiplicity. If the snapshot cannot satisfy the class model, the class model is wrong, the snapshot is wrong, or the scenario is out of scope. Resolve the contradiction before delivery rather than shipping a snapshot that contradicts its types.

## Rendering

Generate the source as `.puml` and render with scripts/render-and-verify.sh. The golden template is assets/templates/object.puml.
