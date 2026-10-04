# Copy standards (shared)

The single source for every string an agent generates for a project outside the interface itself: page and landing copy, the README, docs, the changelog, release notes, the onboarding guide, the app store listing, and error and empty-state copy. Words inside the interface (labels, buttons, errors, empty states as rendered) follow the "Copy in the interface" section of `.claude/references/design-quality.md`, which this file does not repeat. The two files share one voice, the Springer voice in CLAUDE.md, and differ in scope.

The problem this file solves is the same one design-quality.md solves for visuals. A model asked for product copy produces the copy any model produces for any brief of this shape: a contrast reveal in the headline, three benefits with bold labels, a trusted-by row with no names, a closing line that sounds deep and says nothing. The page reads as generated before anyone reads a word of it. The rules below name those defaults so an agent can refuse them, and `spgr-write-page-copy/scripts/copy_lint.py` catches the mechanical subset.

## Contents
- How skills use this reference
- Page structure
- Headlines and calls to action
- Banned phrases
- Structural patterns
- Severity
- The swap test
- The fact rule
- What stays fine
- Sources

## How skills use this reference

| Skill or agent | Section it applies |
|----------------|--------------------|
| spgr-write-page-copy | Every section. The lint runs before the artifact is written |
| spgr-generate-readme, spgr-generate-release-notes, spgr-generate-changelog, spgr-write-onboarding-guide | Banned phrases, structural patterns, the fact rule |
| spgr-write-app-store-listing | Banned phrases, structural patterns, the fact rule, within each store's character limits |
| spgr-write-error-ux-spec | Structural patterns and the fact rule for the explanatory copy. The rendered string follows design-quality.md |
| The Documentation agent | Every generated document passes the lint before it is written |
| spgr-review-pr, the Code Reviewer | A lint finding in README, docs, listing copy, or a UI string file is a P2 on the style axis |

## Page structure

A marketing or brochure page carries its sections in this order unless the brief or the information architecture says otherwise. Each section has one job.

1. Headline. The outcome for the reader, in their words.
2. Subheadline. Who it is for and how the outcome is reached, one sentence.
3. Primary call to action. One per screen above the fold.
4. Proof. A named customer, a sourced figure, or a logo the brief supplies. Nothing invented.
5. Problem. The pain in the vocabulary the discovery research recorded.
6. Solution and benefits. Three to five, each an outcome, each specific to this product.
7. How it works. Three or four steps a new reader can follow.
8. Objections. The reasons a reader would not act, answered plainly.
9. Final call to action. The same action as the first, so the page asks for one thing.

A page type that departs from this order does so for a reason the IA records: a pricing page leads with plans, a docs landing page leads with the first task, a comparison page leads with the comparison.

## Headlines and calls to action

A headline states an outcome or names the category and the audience. Shapes that work:
- `<outcome> without <pain>`
- `The <category> for <audience>`
- `Never <bad event> again`
- `<Verb> <object> in <concrete unit>` when the unit comes from a source

A headline that restates the product category with an adjective in front of it ("The smarter way to track expenses") is a default and fails the swap test below.

A call to action is a verb plus what the reader gets plus, when it matters, the qualifier that removes the risk: `Start tracking expenses`, `Get the report`, `Book a 20-minute walkthrough`. Never `Submit`, `Learn more`, `Click here`, or `Get started` on its own. The action keeps its name through the flow, per design-quality.md.

## Banned phrases

Each row names a phrase that reads as generated and the plain move that replaces it. The lint flags the left column.

| Phrase | Replace with |
|--------|--------------|
| say goodbye to, say hello to | name the pain that stops, or the thing that starts |
| unlock the power of, unleash | say what the reader can now do |
| X, reimagined. X, redefined. | say what changed |
| take X to the next level, supercharge | name the measurable improvement, with its source |
| everything you need, all in one place | list the three things that matter |
| effortless, effortlessly, in just a few clicks, in seconds | state the actual steps or the actual time, from a source |
| join thousands of, trusted by leaders, loved by teams | a named customer or the sourced count, or nothing |
| game-changer, game-changing, revolutionary, cutting-edge, next-generation | delete, say what is different |
| experts agree, studies show, it is well known | cite the study, or delete |
| seamless, seamlessly, frictionless | say what the reader no longer has to do |
| robust, powerful, elegant, intuitive, best-in-class, world-class | delete, show the behavior |
| leverage, utilize, facilitate, empower, enable (as a verb for people) | use, help, let, or the concrete verb |
| whether you are a X or a Y, from startups to enterprises | name the one audience the ICP names |
| in today's fast-paced world, now more than ever | delete the sentence |
| dive in, dive deep, delve | read, open, look at |
| it's not just X, it's Y. Not only X but Y | say Y |

## Structural patterns

Each pattern reads as generated whether or not a banned word appears. The example is the shape, the fix is the move.

| Id | Pattern | Example | Fix |
|----|---------|---------|-----|
| contrast-reveal | Negating a thing nobody claimed to set up the real point | "It's not a tool. It's a teammate." | State the point. "It drafts the reply for you." |
| negation-list | A list of what the thing is not | "No spreadsheets. No chasing. No guesswork." | One sentence on what it does |
| trailing-pile-on | A sentence that keeps adding clauses after the point | "Track every expense, in real time, across every team, wherever they are, automatically." | Stop at the point. Put the second idea in its own sentence |
| rhetorical-question | A question whose only job is to label the next claim | "Tired of chasing receipts?" | Say the pain. "Receipts arrive late and incomplete." |
| colon-reveal | A short setup, a colon, the punchline | "The result: faster closes." | "Closes finish two days earlier." with the source |
| fragment-drumbeat | A run of sentence fragments for rhythm | "Fast. Simple. Done." | One sentence with a verb. At most one fragment per section |
| reflexive-threes | Three of everything because three sounds complete | "Plan, build, and ship." when the product does two of them | The true count |
| synonym-cycling | Rotating names for the same thing to avoid repetition | "the platform", "the solution", "the system", "the tool" | One name, used every time |
| false-range | A range that pretends to cover everyone | "from solo founders to global enterprises" | The audience the ICP names |
| weasel-source | Authority with no name | "industry leaders agree" | A name and a link, or delete |
| abstract-subject | A sentence whose subject is a concept acting on the reader | "Efficiency drives your growth." | A person or the product does something. "You close the books on the second." |
| ing-rider | A trailing participle phrase that asserts an unearned consequence | "..., ensuring nothing slips through." | Delete, or make it a claim with a source |
| vague-connection | Two things asserted as related with no mechanism | "Better data means better decisions." | Name the mechanism or delete |
| dodging-is | Avoiding is, are, has with inflated verbs | "serves as", "boasts", "offers", "provides a way to" | is, has, does |
| stacked-qualifiers | Hedges piled before a claim | "arguably one of the most widely adopted" | Say it or do not |
| bold-decoration | Bold on a label at the start of every bullet | `**Fast.** Loads in under a second.` on every item | Plain sentences. Springer prose carries no bold anyway |
| decorative-heading | Title Case headings, or headings that are slogans | "Built For The Way You Work" | Sentence case, a heading that names the section's content |
| heading-echo | The first sentence repeats the heading | "## Pricing. Our pricing is simple." | Start with new information |
| writing-about-the-document | Copy that narrates itself | "This section covers", "In this guide you will learn" | Start the content |
| chatbot-residue | Conversational framing left in | "Great question!", "Let's explore", "Here's the thing" | Delete |
| knowledge-disclaimer | A model hedging about what it knows | "As of my last update", "I cannot verify" | Resolve the fact or mark it `[NEED: ...]` |
| re-explaining | Telling the reader what the reader already knows | A paragraph defining email to an email product's buyer | Delete and start where the reader is |

## Severity

Three groups, so an editor knows what justifies a rewrite on its own.

- Rewrite on sight: a banned phrase, contrast-reveal, negation-list, colon-reveal, rhetorical-question, weasel-source, chatbot-residue, knowledge-disclaimer, and any unsourced name, number, date, or quote. One of these is enough to fail the section.
- Rewrite in combination: trailing-pile-on, fragment-drumbeat, reflexive-threes, synonym-cycling, abstract-subject, ing-rider, vague-connection, dodging-is, stacked-qualifiers, false-range. Two in one section, or one that recurs across sections, fails the section.
- Fix in place: bold-decoration, decorative-heading, heading-echo, writing-about-the-document, re-explaining, sentences over 25 words, exclamation points. Fix them without a rewrite.

## The swap test

Read the section with the product name removed. If it would sit unchanged on a competitor's site, or on a site in a different category, it is a default and is rewritten. A section passes when it names something only this product, this audience, or this evidence base could supply: the pain in the users' own words from the discovery research, the step the product removes, the figure the brief sourced.

Do not de-slop by inventing. A rewrite that adds a number, a customer, or a claim the inputs do not contain has traded one defect for a worse one. When the specific thing is missing, write the `[NEED: ...]` marker and move on.

## The fact rule

A name, a number, a date, a quote, a customer, a logo, or a comparison appears in copy only when an input supplies it: the PRD content-sources table, a discovery artifact with a source URL, a brief the human wrote, or a file under `docs/inputs/`. Every such item in the page-copy artifact carries its source reference next to it.

When the copy needs a fact the inputs do not hold, write `[NEED: <what is missing and where it would go>]` in its place. Each marker becomes one needs-human-input row in the PRD content-sources table and one intake question. In the built page it ships as a visible `TODO(DEF-<n>)` placeholder under the defaults ledger, which blocks auto-merge, per the decision classes in `.claude/references/pdca-harness.md`. An invented fact is a defect at any severity. A marker is the correct output.

## What stays fine

- A question as an FAQ heading, because that is what an FAQ is.
- One "No card required" or equivalent risk-remover next to the call to action, when it is true.
- A list of three when there are three.
- Repeating the product name instead of cycling synonyms.
- A short sentence after a long one. Varied length is not the drumbeat. Three fragments in a row is.
- Plain is, has, and does.
- Copy that is shorter than the brief expected. Length is never a target.

## Sources

Procedures and pattern names were adapted and rewritten from the copywriting and copy-editing skills in coreyhaines31/marketingskills and from the pattern catalog in blader/humanizer, both MIT. No prose or statistics were carried over.
