# Verifier reliability update — 2026-11-03

The workflow remains human prompt → AI suggestions → independent impact analysis →
AI draft → isolated apply → independent verification → human review. Suggestions
are not approved policy and do not require a separate acceptance step.

## Fixed gaps

- Literal locator tag names accept digits (including h1–h6), while selectors and
  expressions cannot masquerade as tag names. Caller contracts remain strict.
- AI expectation checks validate independently. Valid checks execute when a sibling
  is invalid; indexed errors remain review reasons. An invalid envelope or expanded
  target scope is not trusted. No invalid check is silently treated as passing.
- Discovered references outside a local copy change are `reference_only`, not
  required replacements. AI suggestions never establish a global replacement rule.
  Legacy caller price requests retain their existing reference warnings. Independent
  frozen-policy and rendered marked-fact checks still detect pricing conflicts.
- Literal source outcomes support tag, #id, .class, quoted attribute equality,
  direct-child chains, and :nth-child(n). Text checks compare normalized element
  text. HTML checks compare parsed element signatures, including adjacent sibling
  fragments anchored at a uniquely selected target. Insertions need no fabricated
  old value. Missing/duplicate targets, unsupported selectors and dynamic expressions
  remain unassessed. A different observed value fails the scoped check.
- Source outcome evidence identifies the selector, match counts and candidate line.
  Scope is still separately reported: matching some AI checks does not establish
  that every unrelated element was preserved. AI scope failures never confer human
  authorization. Existing caller element-preservation checks remain available.
- Independent review findings can be `supported`, `conflicting`, or
  `insufficient_evidence`. Supported/conflicting business findings require candidate
  and frozen knowledge citations. Insufficient-evidence findings need candidate
  evidence without inventing a policy quote. Exact citations are validated; semantic
  conclusions remain advisory model judgments. Old unclassified findings retain
  the stricter conflicting-evidence requirement.
- The independent review report inventories new/modified paragraph, list-item,
  link, heading and period-label text for human inspection, including when review is
  unavailable. This inventory is not semantic claim extraction and does not establish
  policy support or defects. New fee/support promises therefore remain visible.
- Review and analysis failures expose sanitized error codes for provider limits,
  timeouts, invalid responses and invalid evidence. Provider messages, credentials
  and raw payloads are not echoed. No clean review is inferred from a failure.
- Human reports include successful builds, browser observations, HTTP status,
  selected axe results, tested CTA reachability, marked-policy checks, and source
  outcomes when those checks actually execute. Workflow summaries carry this evidence.
- Draft planning and implementation use saved intent and complete saved suggestions.
  Generic retry descriptions no longer replace the task. Isolation is managed by the
  workspace; models are told not to invent draft routes, flags or navigation.

## Retrying a review

Repeat `POST /impact/verify` with the existing `change_id`, `draft_id`,
`run_rendered: true`, and `run_ai_review: true` after the provider wait period.
No new suggestions, analysis or draft are required. Browser checks execute again.
Compare returned `candidate_digest` values to confirm source identity across retries;
if they differ, the candidate changed and the results are not the same snapshot.

Older saved analyses retain their recorded expectation validation errors. To exercise
fixed expectation validation, create a new analysis from the saved proposal and bind
its new draft to that analysis. Do not overwrite an old analysis or reuse a draft with
another change ID. Existing candidates can still be reverified with the improved
independent checks, but their missing expectation coverage remains disclosed.

## Validation and limits

Automated regression tests cover the reported heading failure, partial AI contracts,
local-reference false alerts, inserted paragraphs, wrong placement, duplicate matches,
wrong copy, sibling fragments, nth-child, dynamic content, provider 429 redaction,
timeouts, unsupported citations, unsupported promises, successful human-summary
evidence, and saved-intent draft planning. Existing price-conflict, harmful-color,
heading-outline, navigation and immutable-baseline tests remain in the suite.

These changes do not establish full accessibility compliance, search indexing/ranking,
external checkout behavior, conversion improvements, or real-world business truth.
No live-provider or new browser execution is claimed by this update's unit tests.
