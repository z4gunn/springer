# comp-construction

How spgr-render-design-comps builds `tokens.css` and each comp page. Read before writing a page.

## Contents

- [Goal](#goal)
- [Folder layout](#folder-layout)
- [tokens.css](#tokenscss)
- [Page skeleton](#page-skeleton)
- [States on the page](#states-on-the-page)
- [Browser surfaces](#browser-surfaces)
- [Fonts and imagery](#fonts-and-imagery)
- [Linking from the mockup index](#linking-from-the-mockup-index)
- [What not to do](#what-not-to-do)

## Goal

Produce a render that a human can open with a double click and that the capture script can screenshot headless, faithful enough to the proposed tokens that a critique of the capture is a critique of the design system. The comp is high fidelity in identity and low effort in everything else. Two key screens, real copy, real type, real color, no build step.

## Folder layout

```
docs/design/comps/
  <direction-slug>/
    tokens.css
    <entry-screen>.html
    <primary-job-screen>.html
    critique.md
    shots/
      <screen>-375-light.png
      <screen>-375-dark.png
      <screen>-768-light.png
      ...
      capture-report.json
      detect.json            (when the detector ran)
```

The slug matches the direction slug the mockup skill used, so the index can link both.

## tokens.css

The rendered form of the token table. Name every property after its token, so the comp and the design-system artifact share one vocabulary and a reviewer can grep a comp for a raw value and expect zero hits outside this file.

```css
:root {
  color-scheme: light;
  --color-brand: ...;
  --color-surface: ...;
  --color-surface-raised: ...;
  --color-text: ...;
  --color-text-muted: ...;
  --color-border: ...;
  --color-success: ...;
  --color-warning: ...;
  --color-error: ...;
  --color-info: ...;
  --font-display: ...;
  --font-body: ...;
  --text-heading-1: ...;    /* size / line-height pairs per named level */
  --text-body: ...;
  --space-1: ...;           /* the spacing scale as named steps */
  --radius-1: ...;
  --shadow-1: ...;
  --ease-out: ...;
  --duration-fast: ...;
}

:root[data-theme="dark"] { color-scheme: dark; /* every color token restated */ }

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark; /* same dark layer */ }
}

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

Rules:
- The dark layer restates every color token. A light token with no dark counterpart is a gap, raise it against the design-system artifact.
- Semantic colors (success, warning, error, info) are tokens here too, because the error and empty states on the page use them.
- Duration and easing tokens exist even when the comp animates one thing, so the interaction spec can reference them later.
- Set `color-scheme` on the root so native controls and scrollbars follow the theme.

## Page skeleton

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="">   <!-- set by a one-line script from --color-surface -->
  <title>{direction name} - {screen name}</title>
  <link rel="stylesheet" href="tokens.css">
  <!-- optional: one <link> for a sourced web font, or an @font-face block below -->
  <style>
    /* layout and components for this screen, every value a var(--token) */
  </style>
</head>
<body>
  <!-- the screen, in the direction's information architecture -->
  <nav class="comp-nav" aria-label="Comp controls">
    <a href="../../index.html">All directions</a>
    <a href="{other-screen}.html">{other screen}</a>
    <button type="button" data-toggle-theme>Toggle dark</button>
  </nav>
  <script>
    /* the only script: theme toggle writes data-theme on <html>, and theme-color follows */
  </script>
</body>
</html>
```

The comp nav is the one piece of chrome shared across directions. Keep it visually quiet and outside the screen's own layout so it does not enter the critique. The theme toggle exists so the human can flip schemes without the capture script.

## States on the page

A comp page shows the states the screen has, each reachable without a build step:
- Draw the primary component in its default, hover, focus, active, and disabled states side by side in a small strip below the fold, or use a `data-state` attribute the page's own CSS styles.
- Render the loading, error, and empty variants of the screen's main region as separate sections further down, or as separate pages when the layout changes. The capture is full page where the CLI supports it, otherwise the strip is above the fold.
- Error and empty copy is real copy by the copy rules in `.claude/references/design-quality.md`: what went wrong, how to fix it, what to do next.

## Browser surfaces

Set these from tokens on every comp, because their defaults are the first thing a critique notices:
- `::selection` background and color.
- `caret-color` on inputs.
- `:focus-visible` outline with an offset, plus a non-color second signal.
- `accent-color` on form controls.
- `scrollbar-color` where the direction styles scrollbars, otherwise leave it native and say so.
- `text-underline-offset` and `text-decoration-thickness` on links.
- `font-variant-numeric: tabular-nums` on any numeric column.

## Fonts and imagery

- A sourced typeface is a decision the direction makes. Load it once in the head, from a font service link or a self-hosted `@font-face`, and declare the family only in `tokens.css`. Record the family as a token in the design-system artifact. A system stack is a valid choice when the brief fixes it (as a performance or privacy constraint) and is otherwise a default to refuse for the display voice.
- Imagery the brief supplies is used. Imagery it does not supply is a labeled placeholder box, `<div class="ph">[image: founder portrait, warm light]</div>`, styled from tokens so it sits in the composition rather than breaking it. No stock photography, no generated illustration, no SVG scenes.
- Icons come from one library at one stroke weight, inlined as SVG. No emoji, no unicode glyphs as icons.

## Linking from the mockup index

When `direction` mode runs, add a "View hero comp" link per direction to `docs/design/index.html` next to the "Start flow" link, so the human reaches structure and identity from one page. When `system` mode runs, add a "Comps" section to the same index pointing at the selected direction's folder. Keep the index itself in the mockup stylesheet. It is a menu, not a comp.

## What not to do

- No raw color, size, or family value outside `tokens.css`. Grep the folder before returning.
- No framework, no build step, no bundler. Plain HTML and CSS plus the one theme-toggle script.
- No JavaScript animation. Motion is CSS, from the duration and easing tokens, and respects reduced motion.
- No screens beyond the two key ones. No component inventory. No wireframe of every flow.
- No placeholder theater: no Acme, no Jane Doe, no fake metrics, no empty logo rows.
- Do not read the comp source during the critique. Read the captures first.
