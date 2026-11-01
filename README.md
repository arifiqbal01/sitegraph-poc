# SiteGraph POC — Change Impact Intelligence

A **fictional Astro site** and **Dockerized FastAPI service** demonstrating an incremental website graph, optional real AI planning, reviewable AI page drafts, and read-only impact verification. This is a proposal for a possible native Sherpa enhancement, not a Sherpa integration.

## Start

```bash
docker compose up --build
```

Demo site: http://localhost:4321 · API docs: http://localhost:8000/docs

## AI setup (optional, bring your own key)

```bash
cp .env.example .env
# Fill LLM_API_KEY, LLM_MODEL, LLM_API_URL
docker compose up --build
```

Never commit `.env`. The API uses an OpenAI-compatible chat completions endpoint; provider compatibility depends on the model.

## New endpoints

- `POST /graph/reindex`: hash-based incremental update; unchanged files are **not reparsed**.
- `GET /graph`: cached page, knowledge and import/link graph.
- `POST /ai/plan`: **real AI** classifies natural-language change requests, chooses relevant terms and retrieves indexed evidence.
- `POST /ai/draft`: **real AI** generates full replacement Astro page drafts and unified diffs, without changing sources.
- `POST /ai/apply`: after explicit approval, copies the demo pages to an **isolated preview directory** in the API container volume and applies the draft there. It does not modify the original Astro site or publish anything.
- `POST /impact/analyze` and `POST /impact/verify`: original fixture-driven endpoints remain available.

For `/ai/plan` and `/ai/draft`:

```json
{"description":"Reduce the Starter plan price from $29.90 to $19.90 per month on all relevant pages; do not change Growth."}
```

For `/ai/apply`, pass the `draft_id` returned by `/ai/draft`:

```json
{"draft_id":"<draft_id>"}
```

Inspect the returned unified diffs **before** applying. The preview is stored in the persistent `sitegraph_data` Docker volume; it is not served by the Astro dev server in this version. This is intentionally an approval-gated draft workflow, not autonomous production editing.

## How the graph works

The first index reads `demo-site/src` and `knowledge` once, stores nodes and link/import edges in SQLite, and records SHA-256 hashes. Subsequent calls compare file hashes and only reparse changed files; deleted files are removed. Natural-language AI planning queries the stored index, not a full source reparse. Currently this is a **small static graph**; it does not infer dynamic imports, CMS relationships or business-entity equivalence. Those require later work.

## Current limitations

No Playwright/axe-core yet. No automatic integration of AI drafts into `/impact/verify` yet; the existing verification endpoint still uses predefined scenarios. AI draft edits are limited to existing `demo-site/src/pages/*.astro` files. No Astro compilation test or browser preview is run on drafts yet; review the diff and test before any manual publication. Model output is untrusted, and the preview is isolated. AI usage incurs provider costs.

## Tests

```bash
python -m unittest discover -s tests -v
```
