# SEO standards (shared)

The single source for what a public page Springer ships must carry so search engines and AI search tools can find it, read it, and cite it. spgr-check-seo-baseline runs the deterministic half of this file against built HTML. The frontend developer, the code reviewer on its `seo` axis, and spgr-write-ci-pipeline cite this file by repo-relative path and never restate it.

## Contents
- Scope
- On-page rules
- Social cards
- Structured data
- Images
- Sitemap and robots
- Core Web Vitals
- AI-search extractability
- Pricing-page minimum
- What the baseline check covers

## Scope

Every public page a `brochure`, `small`, or `saas` run ships, and every page of a docs site. A page behind authentication is out of scope. On `brochure` the whole product is public pages, so the baseline check is part of the definition of done, which is the CI check. On `small` and `saas` the check runs on the public routes only: the landing page, pricing, docs, blog, legal, and any page a search engine may index.

## On-page rules

- One `<title>` per page, 50 to 60 characters, unique across the site, the page's subject first and the site name last.
- One `<meta name="description">`, 150 to 160 characters. It does not repeat the title and does not end in a stock call to action such as "get started", "learn more", or "try it free". It states what the page answers.
- One `<h1>`. Headings descend in order: an `<h3>` follows an `<h2>`, never an `<h1>`. The heading tree is the page outline, not a styling device.
- One absolute `<link rel="canonical">` per page. The canonical in the served HTML and in the rendered DOM are the same URL. A page never canonicalizes to a different locale.
- `<html lang="…">` set to the page language. A `<meta name="viewport">` is present.
- No `noindex` robots meta on a production page, and no `noindex` in a response header. A staging build may carry it. A production build that still carries it is a blocking defect.
- A URL is under 100 characters, lowercase, hyphen separated, with no trailing-slash inconsistency across the site, and mirrors the breadcrumb path.
- Internal links use descriptive anchor text, never "click here". Every page is reachable from the navigation or another page, with no orphan pages.

## Social cards

Every public page carries `og:title`, `og:description`, `og:image`, `og:url`, and `twitter:card`. The image is an absolute URL, 1200 by 630 pixels, with `og:image:width` and `og:image:height` set. The title and description may differ from the HTML title and meta description when the share context calls for it, and they obey the same no-stock-CTA rule. A `summary_large_image` card is the default for a page with a hero image.

## Structured data

- JSON-LD only, in `<head>`, one or more `<script type="application/ld+json">` blocks. Microdata and RDFa are not used.
- Every block parses as JSON and carries `@context` and `@type`. A multi-type page uses one `@graph` block rather than several loose blocks.
- Every URL is absolute. Every date is ISO 8601 (`YYYY-MM-DD` or a full timestamp).
- The schema describes what is visible on the page. A rating, review, price, or author that does not appear in the rendered page is never emitted. A fabricated review is a blocking defect and a policy violation.
- Active types for a product site: `Organization`, `WebSite`, `WebPage`, `SoftwareApplication`, `Product`, `Offer`, `Article`, `BlogPosting`, `BreadcrumbList`, `Person`, `Event`, `VideoObject`. `LocalBusiness` when the business has a physical location.
- `Product` and `Offer` are server rendered, and the price appears as visible text in the HTML, not only in the markup and not injected by script.
- Google stopped showing `FAQPage` rich results for most sites and retired `HowTo` rich results in 2023. Neither is emitted for rich-result purposes. A real user question-and-answer page may use `QAPage`.
- Validate with the schema.org validator and Google's Rich Results Test before a page ships. A placeholder value in a schema field is a blocking defect.

## Images

- Every `<img>` has an `alt` attribute. A decorative image carries `alt=""`. A content image's alt describes what the image shows, not that it is an image.
- Every `<img>` has `width` and `height` so the browser reserves the box and layout does not shift.
- Below-the-fold images carry `loading="lazy"`. The hero image does not.
- Serve WebP or AVIF with a fallback, and provide `srcset` and `sizes` for a responsive image.
- An image over 200 KB is a finding. Compress or resize it before it ships.

## Sitemap and robots

- `sitemap.xml` at the site root, well formed, under 50,000 URLs and 50 MB per file, split into a sitemap index beyond that. Every listed URL returns 200 and is the canonical form. `lastmod` is accurate or omitted. `priority` and `changefreq` are ignored by search engines and are not relied on.
- `robots.txt` at the site root, valid, naming the sitemap. It never blocks CSS or JavaScript a page needs to render.
- The run records one decision for AI crawlers in the decision log, with two classes kept separate. Search-citability crawlers (Googlebot, OAI-SearchBot, Claude-SearchBot, PerplexityBot) decide whether the site appears in search and AI answers. Training crawlers (GPTBot, ClaudeBot, Google-Extended, Applebot-Extended) decide whether the content trains models. Blocking a training crawler does not block the matching search crawler. The default on a marketing site is to allow the search class and to put the training class to the human as an intake question.
- `/llms.txt` is optional. Google has stated it is not needed for Search. Add it only when the human asks.

## Core Web Vitals

Targets at the 75th percentile: Largest Contentful Paint under 2.5 seconds, Interaction to Next Paint under 200 milliseconds, Cumulative Layout Shift under 0.1. Measure with Lighthouse in the headless browser the run preflight found, and only when that preflight row is `ok`. The measurement is advisory on the review and recorded in the summary. A run without a headless browser states that Core Web Vitals were not measured rather than implying they passed. The structural causes the baseline check does see are blocking or advisory per the table below: a missing image dimension is the usual source of layout shift, and an unsized hero image the usual source of a late paint.

## AI-search extractability

A page that AI search can quote is a page a person can skim. The rules are the same ones a good technical writer applies.
- The first paragraph under the `<h1>` states what the page is about in one or two sentences, so it can be lifted as a definition.
- A heading is phrased as the question or the claim the section answers, not as a label.
- A comparison is a table, not prose.
- A claim that depends on time carries its date. A figure carries its source on the page.
- A price, a limit, and a plan name appear as text in the HTML. A checkmark grid alone is not extractable.
- The page does not ship a separate AI-only variant of its content and does not chunk itself into answer bait. One page, one canonical, one body.

## Pricing-page minimum

A pricing page passes when prices are visible text in the HTML, every tier's limits are written in words next to the tier, `Product` and `Offer` schema are server rendered and match the visible prices, and the page answers trial, cancellation, and limit questions in its own copy. The acceptance check is the paste test: give the page URL to a web-capable model and ask for the plans and prices. A page that cannot be read back correctly is not done.

## What the baseline check covers

`spgr-check-seo-baseline` parses built HTML with no browser and no network, so it answers the structural rules above and nothing that needs a request or a render. It does not measure Core Web Vitals, does not fetch sitemap URLs, and does not validate schema against schema.org. Those steps are named in the skill body as the follow-ups a reviewer runs when the tools are present. The blocking and advisory split lives in the skill body, which is the one place it is stated.
