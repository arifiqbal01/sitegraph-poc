# SiteGraph POC — agent-proposal change impact intelligence

SiteGraph is a read-only impact checkpoint around an AI website editing agent. The fictional Northstar Astro site and Groq-backed demo editor simulate an external agent; **this is not a live Sherpa integration**.

## v0.7.1: bounded model input

Drafts with a saved analysis send only explicitly proposed page targets, or the
contract's allowed edit files. Complete target sources, the original request,
proposed changes and full contract are retained; supporting policy excerpts are
bounded and optional. The full saved verification baseline is unchanged.
`input_summary` records editable files and the serialized editor request size.

`LLM_MAX_INPUT_BYTES` defaults to 24000 and bounds all outgoing model request
bodies. Optional editor excerpts are removed first; oversized required input
returns HTTP 413 before model calls. Provider 413 and 429 are reported separately,
without raw provider bodies or blind retries. See [docs/draft-input.md](docs/draft-input.md).

## v0.7: rendered SEO, accessibility and factual consistency

The nine-page Northstar fixture now includes detailed plans, billing terms,
integration availability, service scope, support and data policies, with a responsive
layout and cross-page business dependencies. It remains explicitly fictional.

An opt-in runner freezes supporting sources, builds baseline and candidate
separately, and checks all routes at desktop and mobile sizes using Playwright
and axe. It reports rendered metadata, internal HTTP destinations, selected
accessibility rules, CTA keyboard reachability and four marked policy facts.
Unavailable browser evidence requires review; it never silently passes.

```sh
npm ci --prefix demo-site
npm ci --prefix tools
./tools/node_modules/.bin/playwright install --with-deps chromium
python -m tools.demo --rendered
```

Five deterministic cases demonstrate correct behavior, wrong destination, noindex,
keyboard exclusion and fact drift, without LLM calls. The optional Docker image,
API `run_rendered` flag, evidence model and limits are documented in
[docs/rendered-demo.md](docs/rendered-demo.md).

## Run

```bash
docker compose up -d --build --force-recreate
```

API: http://localhost:8000/docs · Demo: http://localhost:4321

Set `LLM_API_KEY`, `LLM_MODEL`, `LLM_API_URL` in a private `.env` to enable the optional demo agent. Never commit credentials.

## Connected workflow

1. **Agent proposes** a change, whether prompted by a human, analytics investigation, or autonomous broken-link detection.
2. **POST /impact/analyze** accepts `proposed_changes`, discovers confirmed literal references and incoming links, and persists a baseline with a `change_id`. It does not modify files.
3. **POST /ai/draft** with `description` and `change_id` simulates the external editor, passing the impact report as mandatory context. Returns reviewable diffs and `draft_id`.
4. **POST /ai/apply** with `draft_id` writes an isolated preview, never the live demo sources.
5. **POST /impact/verify** with `change_id` and `draft_id` compares original proposal, baseline and applied preview, reporting changed files, missed references, unexpected changes, removed internal links, and review decision.

Example pre-change proposal:

```json
{
  "agent": "sherpa-simulator",
  "trigger": "human_request",
  "original_request": "Make Starter more affordable",
  "proposed_changes": [{
    "action": "update",
    "target": "/pricing",
    "entity": "Starter",
    "field": "monthly_price",
    "old_value": "$29.90",
    "new_value": "$19.90",
    "reason": "Proposed pricing adjustment"
  }]
}
```

For an autonomous fix, use `"trigger":"agent_discovery"` and describe the agent's intended route/link modification in `proposed_changes`. No human request is required.

```json
{"description":"Change Starter price from $29.90 to $19.90 across all confirmed affected pages","change_id":"<change_id>"}
```

Pass that to `/ai/draft`; then apply the returned draft ID and verify:

```json
{"change_id":"<change_id>","draft_id":"<draft_id>"}
```

## Scope and limitations

The source graph is persisted in SQLite. Reindexing reads files to compare hashes but reparses only changed files. Pre-impact checks use literal references and static internal links, not semantic equivalence or a full dependency resolver. Business knowledge is limited to supplied local Markdown and identified JSON policy facts. Draft editing supports existing Astro pages only, so knowledge changes are correctly reported as unresolved when applicable. The default verification remains source-only. Opt-in rendered verification adds isolated Astro builds, browser/axe checks and local route responses; external live systems and analytics are not connected. The ordinary Astro development server does **not** serve candidate pages. Verification does not prove a business goal was achieved. Existing `/ai/plan` remains a demo agent tool, not SiteGraph's impact authority.

Run tests locally with `python -m unittest discover -s tests -v`.
Install `python -m pip install -r api/requirements.txt httpx` to include the HTTP workflow test; otherwise that one test is skipped. CI installs these dependencies.

## v0.5: optional evidence-grounded impact brief

Add `"use_ai": true` to `/impact/analyze` to request an advisory implementation
brief using the existing `LLM_*` configuration. It defaults to false, so static
analysis and regression tests work without credentials. This is separate from
the editing simulator's `/ai/plan` endpoint.

For example, submit a business-level request without inventing a price:

```json
{
  "agent": "external_agent",
  "trigger": "human_request",
  "original_request": "Make Starter more competitive and improve its pricing CTA",
  "use_ai": true,
  "proposed_changes": [{
    "action": "update",
    "target": "/pricing",
    "entity": "Starter",
    "field": "pricing_presentation",
    "reason": "Investigate options; new price requires confirmation"
  }]
}
```

`implementation_brief` contains the interpreted intent, proposed investigations,
uncertainties, and source citations. Investigations classify references as
`requires_edit`, `potentially_impacted`, or `context_only`; these are advisory
model judgments, not authorization. Every citation must match an exact quotation
on a supplied baseline line. Invalid responses are rejected as a whole. Exact
citation matching does **not** validate the model's reasoning or establish that
a policy is authoritative. Knowledge-policy edits require human confirmation.

The model receives at most 60,000 characters of source evidence (individual
lines capped at 1,000 characters), with truncation disclosed. This bounded POC
uses a supplied source bundle, not an autonomous retrieval agent. Source and
proposal text are treated as untrusted data; prompt injection resilience is not
proven by this implementation.

Statuses are `disabled`, `completed`, or `unavailable`. Provider errors and
invalid evidence produce an explicit unavailable status while retaining static
analysis. Inspect that status before relying on an AI brief. AI recommendations
never change the verifier's expected edits, grant write permissions, or decide
the verification result. Accessibility and checkout recommendations carry
`execution_status: "not_run"`; neither check is implemented here.

Vague proposals can now receive implementation guidance, but verifying a price
replacement still requires explicit old/new values. An unavailable AI brief is disclosed separately. As of v0.6, an unassessed
requested source-edit outcome requires review; see the contract workflow below.

### Regression evaluation

```bash
python -m unittest discover -s tests -v
```

The suite uses temporary baseline files, SQLite indexes, snapshots and previews;
it does not depend on old manual change IDs, Docker volumes or an LLM key.
GitHub Actions runs it on pushes and pull requests. Coverage includes scoped
navigation success, related links left unchanged, authorized removal, missing
destinations, no-op edits, pricing omissions in FAQ and knowledge, unrelated
changes, missing preview files, snapshot/draft identity, and invalid AI evidence.

The v0.5 verifier also reports an unknown navigation target for review, detects
missing preview pages, and treats edits to context-only navigation pages as
unexpected. Multiple identical link occurrences and unintended edits inside an
otherwise expected file remain limitations.

AI tests use mocked responses: they validate orchestration and citation rejection,
not live model quality. A live configured-provider run and rendered/browser
checks remain separate evaluation work. No real Sherpa integration is present.

## v0.6: verify explicit outcomes, not just changed files

A vague proposal with no old/new pair previously returned `no_detected_blockers`
when the pricing page merely changed. It now returns `review_required` unless
an explicit outcome is observed. `outcome_checks` explains the gap. Old analysis
records remain readable; their next verification uses the stricter rule.

Use [scenarios/cta-contract.json](scenarios/cta-contract.json) as the complete
`POST /impact/analyze` request for the Starter CTA demonstration. Set `use_ai`
to false to test without an LLM. Then pass its `change_id` to `/ai/draft`:

```json
{
  "description": "Apply the saved implementation contract exactly: change the Starter CTA to Learn more about Starter and preserve all other content.",
  "change_id": "<returned change_id>"
}
```

Review the diff, apply the draft to the isolated preview, then verify as before.
The valid result has passed contract, outcome and parsed-scope checks. A wrong
CTA, changed destination, changed price/features, ambiguous target or unrelated
same-page edit requires review.

A contract can also be supplied explicitly to `/ai/draft` when the saved analysis
has none. It is persisted with that draft and returned for review; natural-language
instructions alone are not converted into authorization. An analysis contract
cannot be replaced or relaxed by a draft. Create a new analysis to revise it.
Draft creation rejects a page baseline that drifted since analysis.

Contracts contain `allowed_edit_files` and `checks`. Supported checks:

| Kind | Assertion |
| --- | --- |
| `text_equals` | Exact normalized source text of one literal element |
| `attribute_equals` | Exact literal attribute of one element |
| `element_unchanged` | Parsed element structure/content preserved |
| `literal_preserved` | Exact source-literal occurrence count preserved |
| `file_unchanged` | Entire supplied baseline file unchanged |

Each check has a unique `id`, existing `file`, and kind-specific fields. Element
locators use a literal `tag`, optional exact `attributes`, and an optional
`within` ancestor locator. They must identify exactly one baseline element.
Avoid including the attribute being changed in the locator. Dynamic Astro
expressions require rendered verification and cannot establish these assertions.
For multiple proposed changes, set the zero-based `change_index` on outcome
checks; it defaults to 0 and must match that change's target file. One outcome
cannot automatically satisfy every proposal on the same page.

Only an observed text/attribute change or verified explicit old/new replacement
establishes an edit outcome. Invariant checks alone do not prove completion.
`scope_checks` compare parsed source outside declared text/attribute changes.
This comparison is conservative, may require review for legitimate restructuring,
and ignores comments and attribute order. It is not a byte-perfect or rendered
DOM comparison. Components, styles and shared layouts outside the page snapshot
remain outside this check.

### Impact investigations and human review

`impact_investigations` records proposal-selected work before editing.
`investigation_results` reports execution and coverage afterwards:

| Domain | Implemented evidence | Explicitly unverified |
| --- | --- | --- |
| SEO | Source indicators; opt-in rendered metadata and local internal destinations | Search engine indexing, traffic, ranking, production routing |
| Accessibility | Source indicators; opt-in selected axe rules and pricing CTA tab sequence | Full WCAG compliance, complete keyboard and assistive technology coverage |
| Facts | Source invariants; opt-in marked rendered values against supplied policy | Unmarked claims, real-world truth or external authority |
| Business | Existing pricing consistency plus explicit preservation assertions | Approval, policy authority, live checkout, revenue impact |

Source indicators are review signals, not certified violations. Existing source
issues are not reported as newly introduced regressions. Source-only checks can
miss dynamic/component behavior, and local ARIA references may resolve after
rendering. Rendered checks remain `not_run` unless explicitly requested and available; facts/business without explicit
invariants remain `not_assessed`. These optional coverage gaps are disclosed,
while an unassessed requested edit outcome always blocks a clean result. Explicit
fields for contrast, keyboard, accessibility compliance, ranking, indexability,
fact accuracy, checkout, approval, conversions or performance cannot be satisfied
by source assertions alone. Field-name detection is a bounded heuristic, not a
complete natural-language understanding of every business goal.

`human_report` groups verified assertion IDs, review reasons and unassessed work.
It is a compact explanation of the evidence, not a publication approval.
AI impact prompts now explicitly request conditional homepage/FAQ pricing
context, CTA-specific accessibility investigations, and separation of factual
consistency from truth. Prompt quality still needs live-model evaluation.

See [docs/evaluation.md](docs/evaluation.md) for the evaluation scope and next steps.

### v0.6.1: file-final whitespace

The parsed-scope comparison now ignores whitespace-only text nodes at the end
of the document root. A CTA edit plus an added/removed final newline no longer
produces an out-of-contract warning. Interior nodes, element structure and
visible content remain part of the comparison. Verification summaries now count
unresolved scope checks explicitly. Existing analysis/draft IDs can be verified
again after updating the API; no new draft or model call is needed.
