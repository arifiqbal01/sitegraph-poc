# v0.8 — One prompt, independent impact safeguards, final human review

## Purpose

Human prompt → AI suggestions → SiteGraph impact analysis → AI implementation draft
→ isolated application → SiteGraph verification → human review.

There is no proposal acceptance step. Calling this workflow requests completion
through verification in an isolated workspace. It never modifies the original demo
or publishes. Suggestions, evidence, preservation suggestions, assumptions and
unanswered questions travel through the record. Questions do not interrupt the
implementation; they are unresolved items for final human review.

The proposer and editor may infer a poor price, choose low-contrast colours, change
heading structure, introduce a claim, or omit a dependency. SiteGraph must evaluate
the actual result against independently supplied policy and supported website
checks, even when every AI proposal was implemented exactly. The workflow does
not manufacture a passing scenario by requiring humans to pre-approve AI suggestions
or asking the agent to restrict itself to edits that are easy to verify.

## Start with a prompt

Use Swagger at http://localhost:8000/docs. Call **POST /workflow/run**:

```json
{
  "prompt": "Make the Starter pricing card clearer and less intimidating. Suggest and implement improvements to its presentation and copy."
}
```

Defaults are run_rendered=true and run_ai_review=true. A live configured model
provider and the rendered Docker image/local browser dependencies are needed.
No hand-authored proposed_changes or contract is required.

The synchronous response includes:

- workflow_id, change_id and draft_id;
- proposal: concrete AI changes with validated source citations and provenance;
- analysis: references, potential policy conflicts, investigations and an independent
  optional AI impact brief;
- draft: actual diff, bounded input summary and carried proposal context;
- preview: isolated apply result;
- verification: outcome fidelity plus independent policy, source, browser and
  semantic-review evidence;
- review_summary: decision, deduplicated review reasons, assumptions, unanswered
  questions, coverage and limitations;
- status=ready_for_human_review, human_review=not_yet_reviewed and published=false.

A no_detected_blockers decision describes implemented checks, not authority to
publish. Inspect the diff and independent findings before making a human decision.
There is no publication or human-approval mutation endpoint in this increment.

GET /workflow/{workflow_id} reads the saved record using the returned ID. Records
are written atomically. If a stage fails, the HTTP error detail includes the
workflow record, failed stage, safe error and any completed analysis/draft IDs.
A provider 429/413 therefore does not erase earlier evidence. No automatic retry or
restart/resume engine is provided. If necessary, use the retained IDs with the
existing individual endpoints to continue diagnosis. A new workflow call creates
new records rather than overwriting earlier candidates.

## Individual endpoints remain available

POST /impact/propose accepts {"prompt":"..."} and returns an analysis-ready
AgentProposal. Pass that complete result to POST /impact/analyze; its returned
change_id can be used with /ai/draft. These are execution stages, not acceptance
screens. Existing caller-defined contracts remain supported.

POST /impact/verify now accepts run_ai_review alongside run_rendered. Both default
to false on this legacy endpoint for compatibility. The new prompt workflow enables
both by default. Disabling either in /workflow/run is allowed for diagnosis, but
its final decision remains review_required and records reduced coverage.

## AI suggestions and provenance

The proposer is given bounded numbered source evidence and a route inventory.
It returns concrete changes, evidence, preservation suggestions, assumptions,
questions, and optionally a supported verification_contract. The server stamps
AI origin; these expectations never become a caller/human-approved contract.
Invented citations and invalid routes fail structural validation. Actual source
snapshots must still match between proposal and analysis.

Unsupported AI verification checks are recorded as expectation errors and do not
prevent drafting the proposal. Such gaps require final review. Valid expectations
are evaluated separately in suggestion_checks and suggestion_scope_checks.
Outcome checks identify their expectation_origin. Caller contract_checks and
scope_checks remain distinct. No scope check having run is represented as
not_assessed in coverage rather than evidence that unrelated content was preserved.

Draft context carries a bounded independent pre-impact advisory summary, the original prompt, changes, preservation suggestions,
assumptions, unanswered questions and supported AI expectations. Implementation
citations are bounded (six excerpts, 500 characters each), with an explicit
implementation_evidence_truncated flag; complete proposal evidence remains in the
saved analysis/workflow record. Mandatory intent/questions are never silently
truncated to pass the model input budget. Existing v0.7.1 budget/error behavior
continues to apply.

## Independent safeguards

**Before implementation:** source discovery and investigation planning do not depend
on the AI classifying an edit as risky. The supplied policy value is compared with
explicit proposed old/new values, producing potential conflicts with source authority
and limitations. The independent optional impact brief can recommend further
investigations. Neither its warnings nor open questions add an acceptance gate.

**After implementation:**

- Literal marked facts and required occurrences are compared against the immutable
  supplied JSON policy, independently of the AI's plan and check results. Missing
  fact markers cannot evade a required occurrence. Entity/value matching is bounded.
- Source SEO/accessibility investigations run for actual changed pages regardless
  of the proposed field's name. Unpredictable labels cannot disable these checks.
- Separate baseline/candidate builds and browser checks cover metadata, local
  destinations, selected axe rules, pricing CTA keyboard access and marked facts.
- Rendered visible heading levels now identify skipped levels, including h1→h4.
  This is a heading-outline review signal, not a blanket WCAG violation.
- A separately prompted AI reviewer sees the human prompt plus actual baseline,
  candidate and supplied policy sources. It is not given the proposer's expectations,
  a clean verdict or permission to redefine policy. It investigates feature/price/
  promise conflicts, fidelity and uncertainty. Findings require exact source quotes;
  business/fact conflicts need both candidate and supplied-policy evidence. Semantic
  conclusions are advisory. Invalid or unavailable review cannot count as clean.

Business policy conflicts, quality findings, unmet expectations, unanswered questions
and review coverage failures all remain visible to the human. Matching AI expectations
never overrides independent safeguard failures. The models may share a provider;
this is separation of roles and evidence, not statistical independence.

## Reproduce without a provider

```sh
python -m pip install -r api/requirements.txt httpx
python -m unittest discover -s tests -v
npm ci --prefix demo-site
npm ci --prefix tools
./tools/node_modules/.bin/playwright install --with-deps chromium
python -m tools.workflow_demo
```

The demo scripts model responses explicitly. Actual orchestration, analysis, draft
preflight, isolated apply, builds and browser verification run normally. It does
not claim live model generation or semantic-review quality. Existing five fixtures
remain available through python -m tools.demo --rendered.

Correct case: AI proposes a CTA copy change; its supported expectations pass,
independent checks complete, and the result is no_detected_blockers.

Harmful case: AI proposes $19.90, pastel button colours and h4. The editor follows
all three proposals exactly. All proposal outcome checks pass, while rendered
color-contrast, heading_level_skip and policy_mismatch findings require review.
A separate Python regression proves that even a fully satisfied AI price contract
and proposed scope cannot override the independent pricing policy check.

## Local update

After merging, preserve local changes with git fetch origin and git merge origin/main.
Rebuild the optional rendered API without deleting the named data volume:

```sh
docker compose -f compose.yaml -f compose.rendered.yaml up -d --build --force-recreate impact
```

Expected API version: 0.8.0. Existing records/endpoints remain usable. Preserve
private .env and local provider compatibility changes during conflict resolution.
Use a representative low-risk prompt first; no live publication is part of this POC.

## Limits

This is the bounded existing Astro fixture, not an arbitrary CMS/website adapter.
Marked-fact checks are deterministic; unmarked feature/promise interpretation uses
an advisory model and is not comprehensive fact checking. Supplied sources do not
establish external truth, policy ownership, legal compliance or live billing state.
The review can have false positives/misses; exact citation presence is not semantic
proof. Evidence truncation is disclosed and requires review for the independent
post-change AI review. A clean review is never inferred from a failed model call.

No full WCAG/SEO certification, conversion prediction, security sandbox, production
job queue, authentication or real Sherpa runtime integration is claimed. Builds run
trusted repository code. Long-running synchronous requests may need client timeout
adjustments. A new prompt is not an instruction to publish or change originals.
