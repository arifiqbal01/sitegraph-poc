# v0.7 evaluation

Current procedure and boundaries: [rendered-demo.md](rendered-demo.md).
The historical record below describes v0.6 only and is superseded for current
rendered capabilities. Source-only defaults and explicit contracts are preserved.

## Current validation

- 74 Python tests cover existing source behavior, frozen supporting files,
  separate candidate staging, old snapshot refusal and browser failure propagation.
- The expanded nine-page site builds with Astro; pricing layout inspected at
  desktop and mobile widths.
- Five deterministic source scenarios pass expected decision checks.
- Browser scenario results and exact versions are recorded in
  [v0.7-validation.md](v0.7-validation.md).
- Browser CI runs the same five cases and uploads verification reports.
- No live model, external website, production publication or Sherpa integration
  is required or claimed. Optional Docker image execution is separately disclosed.

---

# Historical v0.6 evaluation

The central regression reproduces a vague pricing-presentation proposal followed
by a CTA edit. Changed-file presence must not be mistaken for intent verification.

Tests cover a correct explicit CTA contract, wrong text/destination, altered
price/features, unrelated content in the same file, no-op edits, ambiguous or
dynamic locators, a contract bound through draft/apply/verify, immutable analysis
contracts, and one-outcome-per-proposal coverage. Existing pricing/navigation
regressions remain in the suite.

Source investigation tests cover newly missing headings/layout title, canonical
changes, noindex, unnamed CTA, missing image alt, local ARIA references,
pre-existing source issues, selective domains, and unverified business/fact work.
All tests use isolated fixtures or source strings; AI responses are mocked.

## Limits

This increment does not implement Playwright/axe, live SEO outcomes, external
fact checking, business approval, production CMS adapters or a real Sherpa
integration. Exact source checks establish narrow assertions, not whole-site
safety. Natural-language constraints without explicit checks are not independently
verified. Static source parsing cannot resolve arbitrary Astro or component DOM.

## Next incremental evaluations

1. Run the saved CTA contract through the user's configured provider. Review the
   actual draft; test correct and deliberately incorrect candidate versions.
2. Add an isolated Astro build/render runner, then Playwright and axe checks for
   affected routes. Keep runtime evidence separate from source evidence.
3. Add rendered SEO metadata and destination checks to that same isolated preview.
4. Introduce explicit knowledge-source authority and entity-aware business/fact
   assertions, with human confirmation for policy changes.
5. Evaluate false positives and missed cases against a fixed scenario corpus.

## Executed validation

- 60 tests passed with API dependencies and httpx installed, including the HTTP
  analyze/draft/apply/verify flow and invalid-contract HTTP 422 responses.
- The copy-ready CTA contract was validated against the actual demo source.
- Python compilation and whitespace checks passed.
- No live LLM run, Astro build or browser/axe check was executed for this increment.
