# mockup-construction

How spgr-render-design-mockups builds each HTML page. Read before generating pages.

## Contents

- [Goal](#goal)
- [Page skeleton](#page-skeleton)
- [Linking rules](#linking-rules)
- [Labeled placeholders](#labeled-placeholders)
- [Making directions structurally distinct](#making-directions-structurally-distinct)
- [index.html](#indexhtml)
- [What not to do](#what-not-to-do)

## Goal

Let a human open `docs/design/index.html` with a double click, pick a direction, and walk the primary flow by clicking, then back out and walk a different direction's version of the same flow. The comparison must be about layout and information architecture, so every direction renders the same flow and differs only in structure.

## Page skeleton

Every page is a complete, standalone HTML document, no build step, no JavaScript:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{direction name} - {screen name}</title>
  <link rel="stylesheet" href="../mockup.css">
</head>
<body>
  <header class="mock-banner">
    <span>Mockup: {direction name}</span>
    <span>Screen {n} of {total}: {screen name}</span>
  </header>
  <!-- direction-specific layout for this screen goes here -->
  <nav class="mock-flow-nav">
    <a href="{prev}.html">Previous</a>
    <a href="{first}.html">Restart flow</a>
    <a href="../index.html">All directions</a>
    <a href="{next}.html">Next</a>
  </nav>
</body>
</html>
```

The banner and the flow nav are constant across directions so orientation never changes. Everything between them is the direction's own layout.

## Linking rules

- Use relative paths only, so the mockup works from `file://`.
- Each screen links to the next and previous screen in the flow, to the first screen (Restart flow), and up to `../index.html`.
- The screen's primary action (the button that advances the job) links to the screen it would lead to, so the main path is clickable end to end.
- On the last screen, the Next link points back to the first screen or is omitted, not left dangling.

## Labeled placeholders

Style is low fidelity on purpose. Stand in for real content with labeled boxes:

- Images, avatars, media: `<div class="ph">[image: product thumbnail]</div>`
- Charts: `<div class="ph ph-tall">[chart: reconciliation over time]</div>`
- Real copy: short generic placeholder text is fine. Do not write final product copy.
- Name what the box stands for inside it, so the human reads intent, not decoration.

## Making directions structurally distinct

Two directions rendering the same screen must look structurally different. Vary at least one of these per direction, consistent with the direction's stated interaction model and IA:

- Navigation model: top bar, left sidebar, bottom tab bar, or a wizard with no persistent nav.
- Density: spacious single-column versus a dense multi-column or dashboard grid.
- Content hierarchy: what leads the screen, a primary action versus a data table versus a summary card row.
- Interaction paradigm: step-by-step flow versus a single screen with inline expansion.

If two directions would render a screen the same way, the directions are not distinct enough, escalate rather than ship near-duplicates.

## index.html

`docs/design/index.html` is the entry point. For each direction:

- The direction name as a heading.
- A short neutral sentence naming what makes it structurally distinct (the axes above).
- A link to the direction's first screen to start the flow.

Keep it plain. It is a menu, not a comp. Link the shared `mockup.css`.

## What not to do

- No JavaScript, no frameworks, no build step.
- No external assets, web fonts, CDNs, or network calls. Everything resolves locally.
- No design tokens, brand colors, or final typography. That work happens after a direction is selected, in the design system.
- No screens outside the primary flow. This is a comparison aid, not a screen inventory.
