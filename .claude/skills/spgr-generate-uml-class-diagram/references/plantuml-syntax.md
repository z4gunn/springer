# PlantUML syntax

Glyph reference for the PlantUML class, object, and package diagrams, the default notation for this family. The Mermaid-versus-PlantUML decision table lives in the shared reference at .claude/references/tool-selection.md. PlantUML class, composite, and swimlane layouts need Graphviz `dot`. Render with scripts/render-and-verify.sh.

## Classifiers

```
class Order
abstract class PaymentMethod
interface Refundable
enum Currency { USD\nEUR\nGBP }
class Repository<T>
```

## Members, visibility, classifiers

- Visibility: `+` public, `-` private, `#` protected, `~` package, prefixed on the member.
- Attribute: `- email : String`. Operation: `+ total() : Money`.
- Abstract operation: `{abstract}`, for example `+ {abstract} authorize(amount : Money) : AuthResult`.
- Static member: `{static}`, for example `- {static} taxRate : Decimal`.
- A comma-separated generic such as `Map<K,V>` renders natively in PlantUML, which is one reason this case routes here from Mermaid.

## Relationship glyphs (class diagram)

| Glyph | Relationship |
|-------|--------------|
| `<|--` | generalization |
| `<|..` | realization (dashed) |
| `*--` | composition |
| `o--` | aggregation |
| `-->` | association |
| `..>` | dependency |

The triangle or diamond sits at the end nearest the supertype or whole. Multiplicity and role:
```
Order "1" *-- "1..*" LineItem : contains >
```

## Stereotypes and spots

- Plain stereotype: `<<entity>>`, `<<service>>`.
- Custom spot with a letter and color: `class Card << (M,#ADD1B2) Method >>`.

## Object diagram

Use the `object` keyword. Slot values, not declarations. No multiplicity, no operations.
```
object "order42 : Order" as order42 {
  total = 59.98 USD
}
order42 --> alex : placedBy
```

## Package diagram

Nested `package` or `namespace`, directional acyclic arrows, `<<import>>` and `<<access>>` stereotypes.
```
package "web" {
  package "web.api" {
  }
}
web.api ..> domain : <<import>>
```

## Golden templates

Class assets/templates/class.puml, object assets/templates/object.puml, package assets/templates/package.puml.
