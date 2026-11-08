# Design quality

The Springer bar for visual and interaction design, shared by the design, frontend, mobile, and review skills. It exists because a generated interface tends to converge on the same handful of defaults regardless of subject, and a reader recognizes those defaults as machine output within seconds. The bar has two halves. The choice test keeps a design specific to its brief. The craft floor keeps the built result correct. A design that passes the floor but fails the choice test is competent and forgettable. A design that passes the choice test but fails the floor is a sketch.

Values in this file are detection fingerprints and verification thresholds. Artifacts and generated code still carry tokens only, per the design-system contract. A hex value or a font name in this file is something to recognize, never something to copy into an artifact.

## Contents

- [How skills use this reference](#how-skills-use-this-reference)
- [The choice test](#the-choice-test)
- [Calibration: what generated design looks like right now](#calibration-what-generated-design-looks-like-right-now)
- [Defaults to refuse](#defaults-to-refuse)
- [Craft floor](#craft-floor)
- [Motion standards](#motion-standards)
- [Interface rules](#interface-rules)
- [Copy in the interface](#copy-in-the-interface)
- [Critique procedure](#critique-procedure)
- [Tooling](#tooling)
- [Sources](#sources)

## How skills use this reference

| Skill or agent | Section it applies |
|----------------|--------------------|
| spgr-generate-design-directions | The choice test and the calibration list, when drafting each direction's visual language |
| spgr-render-design-comps | Every section, the critique procedure drives its iteration loop |
| spgr-create-design-system | Defaults to refuse and the craft floor, when fixing tokens and the Do and Don't list |
| spgr-write-interaction-spec | Motion standards, as the bar when no motion-principles document exists |
| spgr-write-component, spgr-implement-feature | Craft floor, motion standards, interface rules, self-critique before the PR opens |
| spgr-review-pr, the Code Reviewer | The design axis on a UI-touching PR: defaults to refuse, the floor, the detector output |
| spgr-run-accessibility-audit | Unchanged. WCAG conformance stays with the Accessibility agent. The floor cites contrast only so a comp is not iterated on a failing pair |

## The choice test

A default is what a model produces for any brief of this shape. A choice is what this brief earns. The test is run twice, once on the plan and once on the built surface.

1. Write the plan before any markup: the palette as named roles, the typefaces and their jobs, the layout concept in one sentence plus an ASCII sketch, the alignment rule, and one sentence naming the single element that will be remembered.
2. Produce the generic version in your head. Ask what the plan would be for a similar prompt with the subject removed. Any part of the plan that survives that substitution unchanged is a default, not a choice.
3. Revise every default. Draw the replacement from the subject's own world: its materials, its vernacular, the setting it is used in, the people the personas describe. A toy for ten-year-olds and a dashboard for treasury analysts should not share a type scale, a palette temperature, or a density.
4. Spend boldness in one place. One element carries the identity. Everything around it is quiet and disciplined. Before finishing, remove one decoration.
5. Where the brief or the brand constraints fix an axis, follow them exactly, even when they ask for something on the calibration list. The brief's own words always win. The test applies only to axes the brief left free.

Record what the test changed and why in the decision log. A direction whose plan survived the test unchanged is suspect and gets a second pass.

## Calibration: what generated design looks like right now

These clusters recur across generated pages regardless of subject. Each is legitimate for some brief. None is a choice when the brief left the axis free.

1. Warm cream ground near `#F4F1EA` with a high-contrast serif display face and a terracotta or clay accent near `#D97757`. The accent is Anthropic's own interaction color, so it reads as a tell on any other brief.
2. Near-black ground with one acid-green or vermilion accent and tinted near-blacks (`#0B0B0B`, `#111`) standing in for black.
3. The broadsheet: hairline rules, zero radius, dense newspaper columns, tracked-out small caps.
4. The SaaS card kit: content chopped into identical rounded cards, one radius everywhere regardless of hierarchy, the same soft gray shadow under each, gradient washes as decoration, a 1px border under a wide soft shadow.
5. The purple cluster: violet, indigo, or purple-to-blue gradients, cyan on dark, gradient text in headings, zero-offset colored glows and radial spotlights behind a hero.
6. Template chrome: a tracked-out all-caps eyebrow above every heading, numbered section markers (01, 02, 03) on content that is not a sequence, meta strings joined with middle dots, labels built as WORD plus spaced dash plus fragment, monospace for small data labels as a technical costume, an arrow glyph appended to every link and button, a pulsing status dot, a marquee, a blinking cursor.
7. Overused faces as the unconsidered default: Inter, Roboto, Open Sans, Lato, Montserrat, Space Grotesk, Plus Jakarta Sans, Geist, and, on the serif side, Fraunces, Recoleta, Playfair, and Instrument Serif set in italic as a hero display.
8. Placeholder theater: Acme and Jane Doe, 99.99 percent uptime, "trusted by" logo rows with no logos, fake screenshots built from nested divs, a BETA or version chip in the hero, an eyebrow chip above the headline.
9. Scattered motion: a fade-and-slide-up entrance on every section, a hover lift on every card, bounce easing, an image that scales on hover.

A comp or a PR that lands in one of these clusters without a brief that asked for it fails the choice test.

## Defaults to refuse

The brief can earn any of these. Reaching for one on a free axis means no decision was made. Rewrite the element rather than soften it.

Page scaffolds:
- A grid of same-size cards, each an icon above a heading above a paragraph, as the page structure. Cards are the lazy container. Nested cards are always wrong.
- The hero-metric template: a big number, a small label, supporting stats, an accent.
- A kicker or eyebrow label above a heading. This one is a ban, not a default. The heading carries its own weight.
- Section numbers unless the sequence itself carries information the reader needs.
- Three equal feature columns. A split header. A zigzag of alternating image-and-text rows beyond two.
- A modal for a task that needs neither interruption nor protected focus.

Surface habits:
- Gradient text. Emphasis comes from weight or size.
- Glass and blur as decoration rather than as a specific, named effect.
- A colored left or right border thicker than 1px on a card, list item, callout, or alert.
- A hard offset shadow outside a world that is actually neobrutalist. One elevation signal per surface, a border or a shadow, never both.
- Sparklines, progress rings, and soft-shadowed rounded rectangles standing in for content.
- Monospace as a costume for technical. Monospace is for code, data, and measurement.
- A system display face as the display voice of a page that claims its own world. Source a face whose character matches the direction and record it as a token.
- Emoji or unicode glyphs standing in for an icon system. Icons come from one library at one stroke weight.
- Geometric masks approximating a photographic subject's edge.
- Stripes, dot grids, and blueprint grids as background texture with no canvas, map, or instrument under them.
- Hand-drawn or sketchy SVG illustration. Real illustration or none. Crisp vector geometry remains first class.
- Light or dark picked by product category. Pick it from the use scene: who, where, under what light.
- Accenting a single word of a headline in a second color or italic. All-caps labels. A label above content that the content does not need.

## Craft floor

Each line is a check on the built result, read from the render or the computed styles, not a statement of intent. Run them together on one capture.

Contrast and color:
- Body and placeholder text at 4.5:1 or better, large text at 3:1 or better, measured on the worst surface each token lands on. A comp with a failing pair is not iterated for taste until the pair is fixed.
- Secondary text on a colored surface is tinted from that hue or from the foreground, never a neutral gray.
- Borders, shadows, and muted text lean toward the background hue. Contrast rises, not falls, on hover, active, and focus.
- One accent. Saturation stays under about 80 percent. No pure black text on pure white in a design that claims warmth.

Depth:
- A shadow carries an offset and a soft blur. Layered ambient plus direct shadows read as light. A zero-offset colored halo is decoration.
- Nested radii are concentric: a child's radius is never larger than its parent's.

Spacing and layout:
- Tight within a group, generous between groups, more space above a heading than below it.
- Everything sits on a grid, a baseline, or an edge. Nothing is placed by accident. Optical alignment beats geometric by a pixel where perception demands it.
- Verified at phone, laptop, and ultra-wide widths. No unwanted scrollbar, no clipped overflow, no content jump when async content lands.
- Safe-area insets respected on mobile.

Type:
- Body measure between 65 and 75 characters, display size at most 6rem, tracking no tighter than -0.04em on display and usually -0.02 to -0.03em, body line height 1.5 to 1.75, no body text below 16px on mobile, no text below 12px anywhere.
- An obvious scale: each step at least 1.25 times the last. Weight steps that read as different weights.
- One family, or two that are clearly distinct in role. Headings carry the personality. The real copy is set at every breakpoint and nothing overflows.
- Tabular numerals in any column that compares numbers. Balanced headings. Curly quotes and a real ellipsis character.

States and surfaces:
- Hover, focus, active, disabled, loading, error, and empty are all drawn, per the design-system state rule.
- The parts the design did not draw still carry it: text selection color, caret color, scrollbar, focus ring, underline offset, form control accent color. Browser defaults in these places are the cheapest signal that a page was assembled rather than built.
- Skeletons mirror the final layout. Long, short, and empty content all render without breaking.

Coverage:
- Every requirement in the brief is present and findable within seconds.

## Motion standards

Use these as the bar when no motion-principles document exists, and translate the chosen values into named duration and easing tokens.

Should it animate:

| Frequency of the action | Decision |
|-------------------------|----------|
| Many times an hour (keyboard shortcuts, command palette, list navigation) | No animation, or nearly none |
| Occasional (modals, drawers, toasts, dropdowns) | Standard animation |
| Rare or first time (onboarding, success, celebration) | Delight is allowed |

Never animate a keyboard-initiated action. Valid purposes are spatial continuity, state indication, explanation, feedback, and preventing a jarring change. "It looks good" on a frequently seen element is not a purpose.

Easing and duration:
- Entering and exiting use a strong ease-out. Movement on screen uses ease-in-out. Hover and color changes use plain ease. Constant motion uses linear. Never ease-in on an interface element.
- Built-in easings are weak. Use strong custom curves, for example an ease-out near `cubic-bezier(0.23, 1, 0.32, 1)` and an ease-in-out near `cubic-bezier(0.77, 0, 0.175, 1)`. A drawer follows the platform sheet curve.
- Button press feedback 100 to 160ms. Tooltips and small popovers 125 to 200ms. Dropdowns 150 to 250ms. Modals and drawers 200 to 500ms. Interface animation stays under 300ms. Exit is faster than enter.
- Delay the first tooltip, show subsequent peers instantly.

Physicality:
- Nothing appears from nothing. Enter from scale 0.9 to 0.97 plus opacity 0, never from scale 0.
- Popovers scale from their trigger with a matching transform origin. Modals are the exception and stay centered.
- Press feedback is a scale to about 0.97 over roughly 160ms on any pressable element.
- Springs are for drag, gestures, and interruptible motion. Keep bounce between 0.1 and 0.3 and reserve it for drag-to-dismiss and playful contexts. Dismiss on velocity, not distance. Damp at boundaries.
- Stagger group entrances by 30 to 80ms and never block interaction while a stagger plays.

Performance:
- Animate transform and opacity only. Never animate width, height, padding, margin, top, or left. Never `transition: all`.
- Prefer CSS transitions (interruptible) over keyframes for anything triggered repeatedly. Use the Web Animations API for programmatic motion.
- Set transform directly on the element, not through a variable on a parent. Keep blur under 20px.
- One orchestrated moment per page beats scattered effects. No identical entrance on every section. Never animate an image on hover.

Accessibility:
- Reduced motion keeps opacity and color changes and removes movement. A jump cut is the minimum fallback.
- Gate hover motion behind a fine pointer, because touch fires false hovers on tap.
- Autoplay motion longer than five seconds beside other content has a pause, stop, or hide control.

## Interface rules

The subset of interface mechanics that the accessibility skills do not already own. Each is a MUST on a UI-touching PR.

- A button for an action, a link for navigation. Never a div with a click handler for navigation. If it looks clickable it is clickable.
- Hit targets at least 24px, 44px on mobile. Mobile input font size at least 16px. Never disable browser zoom.
- Never remove the focus outline without a visible replacement. Sticky and fixed elements never cover a focus ring.
- Never block paste. The submit button stays enabled until the request starts, then shows a spinner and keeps its label. Errors inline next to their field, and the first error takes focus on submit.
- URL reflects state: filters, tabs, pagination, expanded panels. Back restores scroll position.
- Destructive actions confirm or offer an undo window. Toasts and inline validation announce through a polite live region.
- Modals and drawers contain overscroll. Drag, swipe, and pinch have a tap and keyboard alternative.
- Text containers truncate or wrap long content. Flex children get a zero min-width so truncation works. Empty strings and arrays never break the layout.
- Images carry explicit dimensions. Lists beyond about fifty items virtualize. Above-the-fold images preload, the rest lazy-load.
- Dark themes set the document color scheme and a matching theme-color meta. Native selects get an explicit background and color.
- Dates, times, and numbers go through the locale formatting APIs, never hand-built formats.
- Headings are hierarchical, carry a scroll margin, and a skip-to-content link exists. Status is never conveyed by color alone.

## Copy in the interface

Words in an interface exist to make it easier to understand and use. They are design material, not decoration. This section covers the strings rendered inside the interface, and everything outside it (page copy, README, docs, release notes, listing copy) follows `.claude/references/copy-standards.md`.

- Name things by what the person understands, not by how the system is built. Notifications, not webhook configuration.
- Active voice. A call to action says exactly what happens: Save changes, not Submit, not Continue. An action keeps its name through the flow, so Publish produces Published.
- Errors say what went wrong and how to fix it, in the product's voice. They do not apologize and they are never vague. An empty state is an invitation to act, with the action in it.
- Sentence case. Plain verbs. No filler. No marketing adjectives and no filler verbs, per the Springer voice.
- No placeholder theater. Real names from the brief, real numbers from the inputs or an honest label that a value is illustrative.
- Zero em-dashes and en-dashes in visible text. Ration middle dots to one per line.

## Critique procedure

Run this on a captured render, never on the source. Read the screenshot before reading any code, because a reader of the product only ever sees the render.

1. First impression. Read the desktop capture and write three lines: what the surface says it is for, the first three things the eye lands on in order, and whether the memorable element is the one the plan named.
2. Cluster check. Compare the render against the calibration list and the defaults to refuse. Name each hit by its number or bullet. Any hit on a free axis is a finding.
3. Floor check. Walk the craft floor against the computed styles and the three widths. Each miss is a finding with the measured value.
4. Detector pass. When the detector is installed, run it on the comp directory or the built route and merge its JSON findings, which are deterministic and need no interpretation.
5. Motion check. For each animated element, confirm the frequency table verdict, the easing family, the duration band, the reduced-motion branch, and that only transform and opacity move.
6. Copy check. Read every visible string against the copy rules.
7. Verdict. A comp passes when the first impression names the planned element, there is no cluster hit on a free axis, the floor has no miss, and the detector is clean. Otherwise list the findings in severity order (cluster hit, floor miss, detector finding, motion, copy), fix, recapture, and critique the new capture. Cap the loop at three rounds, then escalate with the open list rather than shipping a comp that reads as generated.

Severity on a PR maps cluster hits and floor misses to P1 and motion and copy items to P2, with the detector line, the screenshot path, or the measured value as the evidence the review schema requires.

## Tooling

Both tools are optional external dependencies, like the excalidraw skill. Every skill that cites them runs without them and says so in its report when they are absent.

- Capture. The Playwright CLI (`@playwright/cli`, Apache 2.0) renders a local file or URL headless, resizes the viewport, emulates color scheme and reduced motion, and writes a PNG to disk. The script at `.claude/skills/spgr-render-design-comps/scripts/capture-comps.py` drives it across the width and scheme matrix and writes a capture report. Prefer the CLI over the Playwright MCP server, whose tool schemas load into every subagent's context.
- Detect. The impeccable engine (`impeccable detect <dir|file|url> --json`, Apache 2.0) runs 61 deterministic rules over source, rendered DOM, and computed layout: the side-stripe border, gradient text, the purple and cream palettes, nested cards, overused faces, the kicker, low contrast, layout-property transitions, and drift from a DESIGN.md. It runs with no model, prints a JSON array of findings (antipattern, category, severity, file, line, snippet), and exits 2 when it finds any. It is the deterministic tier of the design check. A global install leaves the launcher at `~/.claude/skills/impeccable/scripts/impeccable`, not on PATH, and the capture script, preflight, and the instance hook all find it there.
- Live hook. A project instance registers `.claude/hooks/design-detect.py` on Edit, Write, and Stop. It forwards the event to the detector, which scans the edited UI file immediately and the whole tree on Stop and returns findings as additional context to the editing agent. The agent triages each finding in its reply: fix a real problem, record the narrowest ignore for a confirmed false positive with the reason, or ask in one line. The hook is advisory and never blocks a write. The review axis is the gate.
- Preflight. `spgr-run-harness/scripts/preflight.py` reports both tools as optional rows so a run knows at open whether the design check runs in full.

## Sources

Mapped, not copied, from the Anthropic frontend-design skill (Apache 2.0), the impeccable craft floor and detector registry by Paul Bakaus (Apache 2.0), the animation standards in Emil Kowalski's skills (MIT), the Vercel web-interface-guidelines (MIT), and the taste-skill fingerprint lists by Leonxlnx (MIT). Rewritten to the Springer voice and the token contract.
