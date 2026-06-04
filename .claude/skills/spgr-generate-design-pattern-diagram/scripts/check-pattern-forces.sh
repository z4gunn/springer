#!/usr/bin/env bash
# Anti-cargo-cult guard. Refuse to generate a pattern diagram unless the pattern's
# defining forces are confirmed present in the supplied code. A pattern is not
# present just because a class is named after it. This guard codifies the rule
# that a diagram over needless indirection teaches the wrong lesson.
#
# It holds the defining-force checklist for all 23 GoF patterns. You supply a
# force-evidence file that lists, one per line, the forces you have confirmed in
# the code (free text, matched case-insensitively against the force keywords).
# The guard names every required force that your evidence does not cover and
# exits non-zero, blocking generation. It exits zero only when every defining
# force for the pattern is accounted for.
#
# Usage:
#   check-pattern-forces.sh <pattern-name> <force-evidence-file>
# The pattern name matches the keys below (case-insensitive, hyphen or space).
# The evidence file is plain text: each line cites where a force is exhibited.
#
# Example evidence line for Observer:
#   Order.publish() loops over a runtime subscribe/unsubscribe listener list
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: check-pattern-forces.sh <pattern-name> <force-evidence-file>" >&2
  exit 2
fi

pattern_raw="$1"
evidence_file="$2"

if [ ! -f "$evidence_file" ]; then
  echo "error: force-evidence file not found: $evidence_file" >&2
  exit 2
fi

# Normalize the pattern key: lowercase, spaces and underscores to hyphens.
pattern="$(printf '%s' "$pattern_raw" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"

# Defining forces per pattern. Each entry is a pipe-separated list of forces.
# Each force is a set of synonym keywords separated by semicolons. The first
# synonym is a readable phrase used in the report; the rest are short tokens the
# evidence prose is matched against (case-insensitive substring). A force counts
# as present when the evidence contains any one synonym in its set. Keep these
# aligned with the defining-forces table in references/pattern-catalog.md.
forces_for() {
  case "$1" in
    abstract-factory) echo "a product family varied together;product family;related product;family of product|a factory interface with one creation method per product;factory interface;createproduct;creation method|concrete factories producing matched families;concrete factor;matched famil" ;;
    builder)          echo "stepwise construction of one product;stepwise;step by step;buildpart;build part|a director that drives the order;director;drives the order|the product decoupled from its assembly;decoupled;separate from how" ;;
    factory-method)   echo "a creation method returning the abstract product;factory method;factorymethod;creation method|subclasses override to vary the product;subclass override;override the method;subclass varies|the creator uses the product abstractly;abstract product;return type" ;;
    prototype)        echo "creation by copying an instance;clone;copy existing;copies itself|a clone operation on the prototype;clone operation;prototype interface|avoids depending on the concrete class;avoids concrete;no new on" ;;
    singleton)        echo "a single shared instance;single instance;sole instance;one shared;single shared|a controlled access point;access point;getinstance|the constructor is not freely callable;constructor;private constructor" ;;
    adapter)          echo "an existing incompatible interface;incompatible;adaptee|a target interface the client expects;target interface;client expects|the adapter translates one to the other;translat;wraps the adaptee" ;;
    bridge)           echo "two independent dimensions of variation;two dimension;independent axes;two axes|the abstraction delegates to an implementor;implementor;delegates to the impl|abstraction and implementation extend separately;extend separately;vary independently" ;;
    composite)        echo "a part-whole tree;part-whole;part whole;tree structure;tree of|a uniform component interface;uniform interface;uniform component;leaf and composite|a composite that forwards to its children;forwards to;recurses over;over each child" ;;
    decorator)        echo "behavior added per instance by wrapping at runtime;runtime wrapping;wrapping;added per instance;per call site;at run time|the decorator shares the component interface;same interface;shares the component|the decorator holds and delegates to the wrapped object;wraps;wrapped;delegates" ;;
    facade)           echo "a complex subsystem of multiple classes;complex subsystem;multiple classes;several subsystem|a single simplified entry point;single entry;one entry point;simplified entry|the facade adds no new behavior, only orchestration;orchestrat;no new behavior" ;;
    flyweight)        echo "a large number of objects sharing intrinsic state;many objects;large number;shared intrinsic|intrinsic state pooled and shared;intrinsic;pooled;shared state|extrinsic state passed in by the client;extrinsic;passed in;supplied by the client" ;;
    proxy)            echo "a surrogate standing in for a real subject;surrogate;stands in;stand-in|the proxy shares the subject interface;same interface;subject interface;shares the subject|the proxy controls access;controls access;lazy;cache;protective;remote" ;;
    chain-of-responsibility) echo "a request handled by one of several handlers;one of several;handled by one;passes along;passes it|each handler holds a successor;successor;next handler;passes to the next|the sender does not know which handler resolves it;sender does not;sender unaware;decoupled sender" ;;
    command)          echo "a request reified as an object;request as an object;request reified;command object|an invoker decoupled from the receiver;invoker;decoupled from the receiver|the command holds the receiver and the action;holds the receiver;holds the action;receiver and action" ;;
    interpreter)      echo "a grammar represented as a class hierarchy;grammar;grammar hierarchy;grammar as|an interpret operation over a context;interpret;evaluate over;over a context|expressions composed into a tree;expression tree;composed tree;tree of expression" ;;
    iterator)         echo "sequential access to an aggregate;sequential access;traverse;traversal;hasnext;next()|traversal state held outside the aggregate;state outside;cursor;external state|the aggregate structure stays hidden;structure hidden;internal structure;encapsulated structure;without exposing" ;;
    mediator)         echo "many-to-many communication collapsed to a hub;many-to-many;many to many;hub;centralized|colleagues reference only the mediator;reference only the mediator;colleagues never reference;only the mediator|the mediator coordinates interaction;mediator coordinat;coordinates the" ;;
    memento)          echo "an externalized snapshot of state;snapshot;saved state;externalized;memento of|the memento is opaque to the caretaker;opaque;caretaker holds|restore returns to a prior state;restore;rollback;roll back;prior state" ;;
    observer)         echo "a one-to-many dependency;one-to-many;one to many;dependents;several listener;several observer|subjects notify observers on state change;notify;publish;on state change;on change|observers subscribe and unsubscribe at runtime;subscribe;unsubscribe;register a listener;add a listener;attach" ;;
    state)            echo "behavior that changes with internal state;behavior changes;state-dependent;changes with state|state encapsulated as distinct classes;state class;distinct state;state as class|the context delegates and transitions;delegates;transition;transitions to" ;;
    strategy)         echo "a family of interchangeable algorithms;interchangeable;family of algorithm;algorithm family;several algorithm|the algorithm selected and swapped at runtime;at runtime;at run time;swap;swappable;selected from|the context delegates to the held strategy;delegates;held strategy;strategy.algorithm" ;;
    template-method)  echo "a fixed algorithm skeleton in a base class;skeleton;template method;fixed algorithm;base-class algorithm|variable steps deferred to subclass hooks;hook;deferred to subclass;subclass overrides the step;primitive operation|subclasses cannot change the overall order;cannot change the order;order is fixed;fixed order" ;;
    visitor)          echo "an operation added without changing the hierarchy;new operation;added without changing;without modifying the element|double dispatch via accept and visit;double dispatch;accept;visit|a stable element hierarchy;stable element;fixed element;element hierarchy" ;;
    *) return 1 ;;
  esac
}

if ! force_spec="$(forces_for "$pattern")"; then
  echo "error: unknown pattern '$pattern_raw'. Use one of the 23 GoF pattern names from references/pattern-catalog.md." >&2
  exit 2
fi

evidence="$(tr '[:upper:]' '[:lower:]' < "$evidence_file")"

missing=0
force_num=0
# Split the force spec on the literal pipe.
IFS='|' read -ra forces <<< "$force_spec"
for force in "${forces[@]}"; do
  force_num=$((force_num + 1))
  found=0
  # Each force is a set of synonym keywords separated by semicolons.
  IFS=';' read -ra synonyms <<< "$force"
  for kw in "${synonyms[@]}"; do
    kw_lc="$(printf '%s' "$kw" | tr '[:upper:]' '[:lower:]')"
    if printf '%s' "$evidence" | grep -qF "$kw_lc"; then
      found=1
      break
    fi
  done
  if [ "$found" -eq 0 ]; then
    # Report the force by its first synonym phrase.
    primary="${synonyms[0]}"
    echo "MISSING FORCE $force_num for $pattern: no evidence of '$primary'" >&2
    missing=$((missing + 1))
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "REFUSED: $pattern is not exhibited by the supplied code ($missing of $force_num defining forces unconfirmed)." >&2
  echo "Do not generate the diagram. Either confirm the missing forces in the code, or pick the pattern the code actually exhibits." >&2
  exit 1
fi

echo "FORCES CONFIRMED: all $force_num defining forces of $pattern are present. Generation may proceed."
