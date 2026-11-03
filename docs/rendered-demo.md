# v0.7 — Change-aware rendered verification

Northstar is a fictional business with nine substantive pages: home, pricing, FAQ,
services, technical SEO, integrations, resources, privacy and contact. Policies cover
billing, seat limits, exports, planned connectors, support, cancellation and retention.
The site has responsive layouts, keyboard focus styles, semantic navigation, a skip
link, comparison table and FAQ disclosures. No customer names, results, certifications
or real commercial operations are fabricated. `.example` canonical/email addresses
are intentional. More realistic fixtures improve evaluation; they do not establish
support for arbitrary production websites or a live Sherpa integration.

## Run locally

From repository root, with Python 3.12 and Node 22.12+:

```sh
python -m pip install -r api/requirements.txt httpx
npm ci --prefix demo-site
npm ci --prefix tools
./tools/node_modules/.bin/playwright install --with-deps chromium
python -m unittest discover -s tests -v
python -m tools.demo --rendered
```

Run one case with `python -m tools.demo --case seo-noindex --rendered`.
Omit `--rendered` for source-only verification. No LLM key/provider is needed for
these deterministic fixtures. Each run creates fresh saved analysis and draft IDs,
labels fixture provenance, applies a new isolated preview and saves verification.json
under that workspace. Original pages, earlier records and contracts are untouched.

| Case | Expected final decision | Required evidence |
| --- | --- | --- |
| correct | no_detected_blockers | Source contract passes; rendered checks completed |
| wrong-destination | review_required | starter-cta-destination contract fails |
| seo-noindex | review_required | Rendered robots contains noindex |
| inaccessible-cta | review_required | CTA is absent from keyboard tab sequence |
| fact-drift | review_required | Marked Starter seat count contradicts supplied policy |

The CLI exits nonzero if the expected decision or required rendered finding is absent.
Thus a browser installation failure cannot count as a successful negative demo.
The accessibility case also makes CTA foreground/background white; whether axe
reports contrast is recorded honestly. Keyboard exclusion is its deterministic check.

## Docker

The default lightweight API image supports source checks. For browser checks use:

```sh
docker compose -f compose.yaml -f compose.rendered.yaml up -d --build impact
docker compose exec impact python -m tools.demo --rendered
```

This builds a larger optional image with Node, Python, Chromium and its libraries.
The existing named data volume is preserved. No volume removal is required.
The Dockerfile is supplied for reproducibility; consult the validation record for
whether a Docker build was executed in the implementation environment.

## API

Create a new analysis after updating; old analyses without a rendered snapshot return
`unavailable` rather than borrowing today's supporting files. Continue the existing
analyze → draft → review → apply workflow. Then:

```json
{"change_id":"<returned analysis ID>","draft_id":"<reviewed applied draft ID>","run_rendered":true}
```

Send this to `POST /impact/verify`. The default is `run_rendered: false`.
`rendered_verification` contains tool/browser versions, baseline/candidate builds,
URLs, viewport/state, per-page metadata, axe violations and incomplete checks,
CTA keyboard reachability, local link responses, fact evidence and limitations.
An unavailable, failed or review-required rendered run makes the final decision
`review_required`. Source assertions remain independently visible.

## Evidence and isolation

At analysis time the complete bounded `src/`, `public/`, Astro config, package files
and supplied `knowledge/product-facts.json` authority are frozen separately from the
legacy page/knowledge baseline. At verification time two temporary projects are
staged from those exact saved files. Only candidate pages come from the applied
preview. Each project builds separately; local static servers expose their outputs.
The original Astro development server is never used as candidate evidence.

Playwright checks all nine snapshot routes at 1440×1000 and 390×844 with reduced
motion enabled. Browser requests are restricted to its local artifact origin. Reports
include a SHA-256 digest of the render snapshot. Temporary servers and builds are
cleaned up. Dependencies are installed ahead of time, not fetched by verification;
the saved lockfile must match the current dependency definition. This checks a lock
match, not a cryptographic audit of installed node_modules.

These builds execute trusted project/config code. This synchronous opt-in POC runner
is for local use; it is not an authenticated public build service or a sandbox for
untrusted arbitrary repositories. Build and runner timeouts are bounded. A supplied
`SITEGRAPH_CHROMIUM_EXECUTABLE` may select an existing local Chromium binary; its
actual version is recorded. Normal installations use Playwright's matching browser.

## Deliberate limits

- SEO: rendered title, description, canonical, robots, h1 and internal destinations.
  Metadata changes require review; no inference of authorization from prose. There
  is no search engine indexing/ranking test, schema/hreflang audit or SEO score.
- Accessibility: selected WCAG A/AA axe rules plus the pricing CTA tab sequence.
  Axe incomplete results remain in evidence for manual review. Passing this subset
  does not prove compliance, screen-reader quality or complete interaction coverage.
- Facts: exact marked occurrences and required routes for four policy facts, against
  an explicitly identified fictional policy authority. Hidden, missing, unknown or
  mismatched marked occurrences are flagged. Unmarked claims and external commercial
  truth are not assessed. Changing policy requires a new agreed analysis; the agent
  cannot rewrite the authority to pass its own candidate.
- Reports retain baseline issues, not only regressions: existing accessibility issues
  are labelled baseline_present and still require review. No publication occurs.
- Dynamic/CMS adapters and production deployment are outside this increment.
