# Class diagram

How to build the class view: classifiers, members, and the five relationship kinds. Notation glyphs live in mermaid-syntax.md and plantuml-syntax.md. Family quality rules and the render loop live in the shared standards at .claude/references/diagram-standards.md.

## Classifiers

Make the classifier kind visible, not just a box. Use the native keyword or stereotype:
- class, abstract class, interface, enum.
- Mark abstract operations and the abstract class itself. Mark static members.
- A generic type carries its type parameter, for example `Repository<T>`. A comma-separated generic such as `List<K,V>` is a Mermaid trap and routes to PlantUML.

## Members and visibility

- Visibility markers: `+` public, `-` private, `#` protected, `~` package.
- Members are `name : Type` for attributes and `name(params) : Return` for operations.
- Model only the members that serve the diagram's question. Suppress trivial getters, setters, and boilerplate constructors. Over-detail drowns the structure. A class that shows ten accessors and no real behavior teaches nothing.

## The five relationship kinds

| Kind | Means | Diamond or arrow |
|------|-------|------------------|
| Generalization | subtype is a kind of supertype | hollow triangle at the supertype |
| Realization | class implements an interface | hollow triangle, dashed line, at the interface |
| Composition | whole owns the part's lifecycle | filled diamond at the whole |
| Aggregation | whole references a shared or independent part | hollow diamond at the whole |
| Association | one type uses or links to another | plain arrow, no diamond |
| Dependency | transient use, a parameter or return type | dashed arrow `..>` |

Dependency is the sixth, weakest link. Use it for a transient reference, not a structural field.

## Choosing composition, aggregation, or association

Pick by lifecycle, not by intuition:
- Composition when destroying the whole destroys the part, and the part belongs to exactly one whole. An Order and its LineItems.
- Aggregation when the part can outlive the whole or be shared. An Order and the Customer who placed it.
- Plain association when neither owns the other, they only reference each other.

The diamond always sits at the whole. The three common semantic errors:
1. Putting the diamond on the part instead of the whole.
2. Using composition where the part is shared, which lies about ownership.
3. Drawing realization as generalization, which confuses "implements" with "is a kind of".

## Multiplicity and roles

Always label multiplicities at both ends and name the association role. An edge with no multiplicity and no role is ambiguous. Use `1`, `0..1`, `1..*`, `0..*`, or an exact count. Put the reading-direction marker on the role when it clarifies, for example `Order "1" *-- "1..*" LineItem : contains >`.

## Stereotypes

Use stereotypes to carry a classifier role the keyword cannot, for example `<<entity>>`, `<<service>>`, `<<repository>>`. PlantUML supports a custom stereotype spot, for example `<< (S,#color) Service >>`. Mermaid carries reduced stereotype fidelity, which is one reason a stereotype-heavy class view stays on PlantUML.

## One question per diagram

One class diagram answers one question for one audience at one altitude. Prefer several focused diagrams over one wall of members. Use a package diagram as the map and class diagrams for the detail of each package.

## Notation and rendering

Default to PlantUML. Use Mermaid `classDiagram` only for a standalone class view destined for Markdown, and only after the trap linter passes. Render every generated source with scripts/render-and-verify.sh before delivery. See the syntax references for the exact glyphs.
