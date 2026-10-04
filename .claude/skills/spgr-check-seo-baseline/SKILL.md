---
name: spgr-check-seo-baseline
description: Produce a PASS or GATE verdict per built public page against the structural SEO standards (title, description, H1, canonical, lang, viewport, noindex, social cards, JSON-LD, image alt and size, sitemap and robots). Use before a PR on a brochure site or any public page, as the brochure CI check, and as a code-review finding source.
---

# check-seo-baseline

## Purpose

A public page that search engines and AI search tools cannot read is a page the product does not have. Springer's brochure profile ships nothing but public pages, and its definition of done is the CI check. This skill is the deterministic SEO half of that check. It parses built HTML with no browser and no network and reports every rule in `.claude/references/seo-standards.md` that static markup can answer, as a per-page table and one verdict. The procedure is mechanical, so it needs no reasoning budget and dispatches at the deterministic tier.

## Inputs

| Field | Description |
|-------|-------------|
| `built_output` | The built output directory, or a list of HTML files. When omitted the script looks for `dist/`, `out/`, `build/`, `public/`, or `_site/` under the project root. |
| `site_root` | Optional. The directory holding `sitemap.xml` and `robots.txt` when it is not the built output directory. |
| `profile` | The run profile from the run brief. `brochure` runs strict. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `seo_report` | The script's JSON report: per-page check results with severity and detail, the root checks, counts of blocking and advisory failures, and the verdict. |
| `verdict` | `PASS` when no blocking check fails, `GATE` otherwise. |

## Procedure

1. Locate the built output. Build the site first if the output directory is absent, with the project's own build command. Do not run the check on source templates, because the rendered head is what a crawler reads.

2. Run the script. On `brochure` pass `--strict`, which promotes every advisory check to blocking, because the whole product is public pages and the check is the definition of done. On `small` and `saas` run it on the public routes only.

   ```bash
   python3 .claude/skills/spgr-check-seo-baseline/scripts/seo_baseline.py dist --json
   python3 .claude/skills/spgr-check-seo-baseline/scripts/seo_baseline.py dist --strict --json
   ```

   The script exits 0 on PASS, 1 on GATE, and 2 when it found no HTML file. Exit 2 is a build or path problem, never a pass. Fix the target and run it again.

3. Map the results. A failed blocking check is a P1 finding on the `seo` review axis, with the script line as evidence. A failed advisory check is a P2 finding on the same axis. On a frontend developer unit, fix every blocking failure before opening the PR and fix advisory failures where the fix is in the diff's own files.

4. State what was not measured. The script does not measure Core Web Vitals, fetch the sitemap's URLs, or validate schema against schema.org. When the run preflight found a headless browser, run Lighthouse on the built page for the performance and SEO categories and record the figures as advisory. Otherwise write in the review summary that Core Web Vitals were not measured.

5. Return the JSON report and the verdict to the calling agent. The calling agent records the verdict with spgr-log-decision when it changes a PR's state.

## Check table

| Check | Severity | Rule |
|-------|----------|------|
| `title-present` | blocking | exactly one non-empty `<title>` |
| `description-present` | blocking | a meta description is present |
| `h1-single` | blocking | exactly one `<h1>` |
| `noindex-absent` | blocking | no `noindex` in the robots meta |
| `canonical-present` | blocking | one absolute canonical link |
| `lang-present` | blocking | `<html lang>` is set |
| `viewport-present` | blocking | a viewport meta is present |
| `jsonld-valid` | blocking | every JSON-LD block parses and carries `@context` and `@type` |
| `img-alt` | blocking | every `<img>` has an `alt` attribute |
| `title-length` | advisory | 50 to 60 characters |
| `description-length` | advisory | 150 to 160 characters |
| `description-distinct` | advisory | does not repeat the title or end in a stock call to action |
| `heading-order` | advisory | headings descend one level at a time |
| `og-complete` | advisory | `og:title`, `og:description`, `og:image`, `og:url` |
| `twitter-card` | advisory | `twitter:card` present |
| `img-dimensions` | advisory | every `<img>` has `width` and `height` |
| `jsonld-active-types` | advisory | no `FAQPage` or `HowTo` |
| `sitemap-present`, `sitemap-size` | advisory | `sitemap.xml` at the root, well formed, under 50,000 URLs |
| `robots-present` | advisory | `robots.txt` at the root |

`--strict` makes every row blocking.

## Notes

- The report is not a typed artifact. It carries no envelope and is not routed through spgr-write-artifact. The code-review artifact that cites it is the typed record, and the `seo` axis is in the code-review schema's finding axis enum.
- The bar is `.claude/references/seo-standards.md`. This skill never restates a rule, it checks the ones static HTML can answer and names the rest in step 4.
- The script is stdlib only and runs with no model. Dispatch it at the deterministic tier, the same row as the comp capture script.
- This skill has no Phase 1 vault spec. It was authored to the Springer build standards as a net-new capability.
