# pricing-page

The pricing-page spec section of the entitlement map: what the page that sells the plans must show, how a paywall behaves inside the product, and the check that proves the page is readable by a human buyer and by a machine. Read when the procedure reaches the pricing-page step.

## Contents

- [Why the map owns this](#why-the-map-owns-this)
- [Tier presentation](#tier-presentation)
- [Price and limit legibility](#price-and-limit-legibility)
- [Structured data](#structured-data)
- [FAQ coverage](#faq-coverage)
- [Paywall timing](#paywall-timing)
- [Dark-pattern ban list](#dark-pattern-ban-list)
- [The paste test](#the-paste-test)
- [Spec section shape](#spec-section-shape)

## Why the map owns this

The entitlement map is the one place the plan-to-feature relationship is written down, so it is also the one place the pricing page can be derived from without drift. A pricing page written from memory of the plans shows a limit the service layer does not enforce, or hides one it does. The spec section here is a projection of the plan table and the matrix, and a change to either re-derives it.

## Tier presentation

- Show three or four tiers. Two tiers give no anchor, five or more force a comparison the buyer will not finish.
- Mark exactly one tier recommended, and place it so the eye lands on it first. The recommended tier is the one the target ICP in the plan table buys, not the most expensive one.
- Anchor the recommended tier against the one above it, so its price reads as the sensible choice rather than the cheapest.
- Offer a monthly and an annual toggle and state the annual discount as a number next to the toggle. A toggle with no stated discount asks the buyer to do arithmetic.
- Order the tiers from least to most expensive, left to right or top to bottom, and keep the feature rows in the same order on every tier.
- A tier whose price is quoted on request is allowed once, on the top tier only. A page where every tier says contact us is not a pricing page.

## Price and limit legibility

- Write every price as visible text in the HTML, not inside an image, a canvas, or a script-rendered node that is empty in the server response.
- Write per-tier limits in words, with the number and the unit, for example "5 projects, 3 seats, 10 GB storage". A checkmark alone says a feature exists and hides the limit the matrix enforces.
- Use the same feature names on the page as in the entitlement matrix, so a support question about a limit resolves to one row.
- Name the unit of the billing model on the page (per seat, per month, per thousand events) wherever a price appears.

## Structured data

- Emit Product and Offer JSON-LD for the plans, one Offer per tier per billing period, with `price`, `priceCurrency`, and the billing period, rendered in the server response. A pricing block that only exists after client-side JavaScript runs is not read by every crawler that matters.
- Keep the structured prices equal to the visible prices. A mismatch is a defect in the page, not in the schema.
- The SEO baseline check in `.claude/references/seo-standards.md`, when present in the repository, verifies the JSON-LD shape. This section fixes the content.

## FAQ coverage

The page answers these questions in plain text, each as its own heading and short answer, because they are the questions a buyer asks before paying and the questions a model is asked when a buyer delegates the research:

- What the trial includes, how long it runs, and whether a card is required.
- How cancellation works and what happens to data after it.
- What each limit means and what happens when it is reached (the hard gate and the soft warning from the degradation section of the map).
- How plan changes are prorated.
- Which payment methods and currencies are accepted.

## Paywall timing

A paywall is an upgrade gate the product shows a user who has reached the edge of their plan. The entitlement map specifies when it may appear.

- Show the paywall after a value moment and before a frustration moment: once the user has done the thing the product is for, and before a repeated block makes them leave.
- Never show a paywall during onboarding. A user who has not reached the activation event has nothing to upgrade for.
- Never interrupt a workflow mid-step with a paywall. Gate at the boundary of the action, before it starts or after it completes, never between.
- Warn about a trial ending at seven days, three days, and one day before the end, each warning naming the date and what changes.
- A soft warning fires at the approach threshold the degradation section sets, and the hard gate fires at the limit. The paywall is the hard gate's UI.

## Dark-pattern ban list

None of these appear on the pricing page or in a paywall. A finding on one is a blocking finding in review.

- A close or dismiss control that is hidden, delayed, low contrast, or placed off the visible area.
- A plan selector where the pre-selected or visually dominant option is not the one the user came for, or where the recommended tier changes between the page and the checkout.
- Guilt copy on the decline path, for example a decline button that reads as a self-criticism.
- A trial that converts to paid without the three warnings above.
- A monthly price shown large with the annual commitment in small print.
- A countdown or scarcity claim that is not true.
- A cancellation path longer than the signup path.

## The paste test

The acceptance check for the pricing-page spec section, run against the built page before the story is done and again after any pricing change:

1. Give the page URL to a web-capable model with no other context and ask it to list every plan, its monthly and annual price, and its limits.
2. Every tier, every price, and every limit from the plan table must come back correctly. A missing tier, a wrong price, or a limit reported as a checkmark fails the check.
3. Record the model, the date, and the transcript excerpt in the decision log.

A page that fails the paste test is not readable by the buyers who delegate the research, and usually fails a human skimming it as well.

## Spec section shape

The pricing-page section of the entitlement-map artifact carries:

- `tiers_shown`: the ordered list of tiers on the page, the recommended one flagged, each with monthly and annual price and the limit phrases in words.
- `annual_discount`: the stated discount.
- `structured_data`: the Product and Offer JSON-LD plan, one Offer per tier per period.
- `faq`: the question list and the answer source for each (the map section or the billing spec it is derived from).
- `paywall_rules`: the timing rules above with the activation event the PRD names and the trial warning schedule.
- `banned_patterns_checked`: the ban list, each item marked checked at review.
- `paste_test`: the acceptance check record.
