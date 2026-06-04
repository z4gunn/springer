# Pattern catalog

Lookup table keyed by pattern name for all 23 Gang of Four patterns. Query a row by pattern name to auto-select the canonical role vocabulary for the structure view and the signature collaboration scenario for the sequence view. Each row also names the GoF category and the defining forces the anti-cargo-cult guard checks for. Use the role names in the Roles column exactly so a reader recognizes the pattern on sight.

## Contents
- How to read a row
- Creational patterns
- Structural patterns
- Behavioral patterns
- Defining-forces reference for the guard

## How to read a row

- Category: Creational, Structural, or Behavioral. Drives which golden example to copy.
- Roles: the canonical GoF role names, in collaboration order where it matters. These become the class names in the abstract structure view.
- Signature scenario: the one runtime collaboration that teaches the pattern. This becomes the sequence-diagram shape.

## Creational patterns

| Pattern | Category | Roles | Signature scenario |
|---------|----------|-------|--------------------|
| Abstract Factory | Creational | AbstractFactory, ConcreteFactory, AbstractProduct, ConcreteProduct, Client | Client holds an AbstractFactory, calls createProductA() and createProductB(); the ConcreteFactory returns a matching family of ConcreteProducts. |
| Builder | Creational | Director, Builder, ConcreteBuilder, Product | Director drives Builder step by step (buildPartA(), buildPartB()), then getResult() returns the assembled Product from the ConcreteBuilder. |
| Factory Method | Creational | Creator, ConcreteCreator, Product, ConcreteProduct | Creator template method calls its own factoryMethod(); the ConcreteCreator override returns the ConcreteProduct the rest of the method then uses. |
| Prototype | Creational | Prototype, ConcretePrototype, Client | Client calls clone() on a Prototype; the ConcretePrototype returns a copy of itself, avoiding a new on a concrete type. |
| Singleton | Creational | Singleton, Client | Client calls Singleton.getInstance(); the first call constructs the sole instance, every later call returns the same one. |

## Structural patterns

| Pattern | Category | Roles | Signature scenario |
|---------|----------|-------|--------------------|
| Adapter | Structural | Target, Adapter, Adaptee, Client | Client calls request() on the Target interface; the Adapter translates it into a specificRequest() on the wrapped Adaptee. |
| Bridge | Structural | Abstraction, RefinedAbstraction, Implementor, ConcreteImplementor | Abstraction.operation() delegates to the held Implementor.operationImpl(); abstraction and implementation vary on separate axes. |
| Composite | Structural | Component, Leaf, Composite, Client | Client calls operation() on a Component; a Composite forwards operation() to each child, a Leaf does the work directly, uniformly across the tree. |
| Decorator | Structural | Component, ConcreteComponent, Decorator, ConcreteDecorator | Client calls operation() on a ConcreteDecorator; it adds behavior, then delegates operation() to the wrapped Component, which may be another decorator. |
| Facade | Structural | Facade, Subsystem classes, Client | Client calls one Facade method; the Facade orchestrates several Subsystem calls behind a single simplified entry point. |
| Flyweight | Structural | Flyweight, ConcreteFlyweight, FlyweightFactory, Client | Client asks FlyweightFactory.getFlyweight(key); the factory returns a shared ConcreteFlyweight, and the Client supplies the extrinsic state to operation(state). |
| Proxy | Structural | Subject, Proxy, RealSubject, Client | Client calls request() on the Proxy; the Proxy controls access (lazy-load, check, cache), then forwards request() to the RealSubject. |

## Behavioral patterns

| Pattern | Category | Roles | Signature scenario |
|---------|----------|-------|--------------------|
| Chain of Responsibility | Behavioral | Handler, ConcreteHandler, Client | Client sends handleRequest() to the first Handler; each ConcreteHandler either handles it or passes it to its successor along the chain. |
| Command | Behavioral | Command, ConcreteCommand, Invoker, Receiver, Client | Invoker calls execute() on a held Command; the ConcreteCommand calls action() on its Receiver, decoupling request from execution. |
| Interpreter | Behavioral | AbstractExpression, TerminalExpression, NonterminalExpression, Context, Client | Client builds an expression tree, then calls interpret(Context); each NonterminalExpression recurses into its children, TerminalExpressions evaluate directly. |
| Iterator | Behavioral | Iterator, ConcreteIterator, Aggregate, ConcreteAggregate, Client | Client gets an Iterator from the Aggregate, then loops hasNext() and next() to traverse without exposing the Aggregate's internal structure. |
| Mediator | Behavioral | Mediator, ConcreteMediator, Colleague, ConcreteColleague | A Colleague notifies the Mediator of an event; the ConcreteMediator coordinates the other Colleagues, so colleagues never reference each other directly. |
| Memento | Behavioral | Originator, Memento, Caretaker | Caretaker calls Originator.save() to get a Memento, holds it opaquely, and later passes it to Originator.restore(memento) to roll back state. |
| Observer | Behavioral | Subject, ConcreteSubject, Observer, ConcreteObserver | ConcreteSubject state changes, it calls notify(), which loops update() over every registered ConcreteObserver, each then reads the new state. |
| State | Behavioral | Context, State, ConcreteState | Client calls Context.request(); the Context delegates to its current State.handle(), which does the work and may transition the Context to another ConcreteState. |
| Strategy | Behavioral | Context, Strategy, ConcreteStrategy, Client | Client configures a Context with a ConcreteStrategy; Context.execute() delegates to the held Strategy.algorithm(), swappable at runtime. |
| Template Method | Behavioral | AbstractClass, ConcreteClass | Client calls the AbstractClass templateMethod(); it calls the fixed steps and the primitive hooks that ConcreteClass overrides, fixing the skeleton. |
| Visitor | Behavioral | Visitor, ConcreteVisitor, Element, ConcreteElement, ObjectStructure | Client walks the ObjectStructure calling accept(visitor) on each Element; each ConcreteElement calls back visitConcreteElement(this) for double dispatch. |

## Defining-forces reference for the guard

The anti-cargo-cult guard refuses to draw a pattern unless its defining forces are present in the supplied code. The forces below are the minimum that distinguish each pattern from a coincidental shape. A pattern is not present just because a class is named after it.

| Pattern | Defining forces that must be present |
|---------|--------------------------------------|
| Abstract Factory | A product family of two or more related products, varied together; a factory interface with one creation method per product; concrete factories producing matched families. |
| Builder | Stepwise construction of one product; a director that drives the order; the product is decoupled from how it is assembled. |
| Factory Method | A creator with a method whose return type is the abstract product; subclasses override the method to vary the concrete product; the creator uses the product without naming the concrete type. |
| Prototype | Object creation by copying an existing instance; a clone operation on the prototype interface; the client avoids depending on the concrete class to instantiate. |
| Singleton | A single shared instance; a controlled access point; the constructor is not freely callable from outside. |
| Adapter | An existing incompatible interface (the adaptee); a target interface the client expects; the adapter translates one to the other without changing the adaptee. |
| Bridge | Two independent dimensions of variation; an abstraction that holds and delegates to an implementor; abstraction and implementation extend separately. |
| Composite | A part-whole tree; a uniform component interface for leaf and composite; a composite that forwards operations to its children. |
| Decorator | Behavior added per instance at runtime by wrapping; the decorator shares the component interface; the decorator holds and delegates to the wrapped component. |
| Facade | A complex subsystem of multiple classes; a single simplified entry point; the facade adds no new behavior, only orchestration. |
| Flyweight | A large number of objects sharing intrinsic state; intrinsic state pooled and shared; extrinsic state passed in by the client at call time. |
| Proxy | A surrogate standing in for a real subject; the proxy shares the subject interface; the proxy controls access (lazy, remote, protective, or caching). |
| Chain of Responsibility | A request handled by one of several handlers; each handler holds a successor; the sender does not know which handler resolves it. |
| Command | A request reified as an object; an invoker decoupled from the receiver; the command holds the receiver and the action to perform. |
| Interpreter | A grammar represented as a class hierarchy; an interpret operation over a shared context; expressions composed into a tree. |
| Iterator | Sequential access to an aggregate's elements; traversal state held outside the aggregate; the aggregate's internal structure stays hidden. |
| Mediator | Many-to-many colleague communication collapsed to a hub; colleagues reference only the mediator; the mediator coordinates interaction. |
| Memento | Externalized snapshot of an originator's state; the memento is opaque to the caretaker; restore returns the originator to a prior state without exposing internals. |
| Observer | A one-to-many dependency; subjects notify registered observers on state change; observers subscribe and unsubscribe at runtime. |
| State | Behavior that changes with internal state; state encapsulated as distinct classes; the context delegates and transitions between states. |
| Strategy | A family of interchangeable algorithms; the algorithm selected and swapped at runtime; the context delegates to the held strategy. |
| Template Method | A fixed algorithm skeleton in a base class; variable steps deferred to subclass hooks; subclasses cannot change the overall order. |
| Visitor | An operation added to a class hierarchy without changing it; double dispatch via accept and visit; a stable element hierarchy. |
