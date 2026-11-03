# Bounded drafting input — v0.7.1

## Problem and fix

The expanded fixture previously sent all nine page sources and the full saved
analysis to the editor, with duplicated context and an additional model plan.
A user observed an upstream HTTP 413 during the three-page pricing/design test.
That error alone does not identify a provider's byte, token, or quota threshold.

Draft input now follows the saved proposal's explicit page targets. If a contract
exists, its allowed_edit_files defines the supplied edit scope. Each editable file
is supplied completely. Unresolved targets fail rather than falling back to all
pages. Returned edits outside the supplied file set are rejected before persistence.
Caller-specified contracts remain immutable. Without an analysis, legacy drafting
still uses existing demo pages, subject to the same file and request-size limits.

The editor receives the full original request, full proposed changes, full bound
contract, preservation instructions and up to twelve relevant policy excerpts
(maximum 500 characters each, marked when truncated). It does not receive the full
report, duplicated graph/search results or unbounded planner prose. The planner
still returns its advisory plan, using target-only graph metadata; that prose does
not authorize edits or define acceptance checks. Related references are context,
not additional edit permissions. A cross-page update needs explicit targets or
contract scope for each editable page.

## Budget and errors

LLM_MAX_INPUT_BYTES defaults to 24000. The guard measures the UTF-8 serialized
request, including model, system/user messages and JSON wrapper. This is a byte
budget, not an exact token count or a promise that any particular provider accepts
it. It applies to all model calls, including optional analysis and standalone plans.
If an optional AI analysis exceeds it, static analysis remains available and the
advisory brief reports unavailable, as with other provider failures.

Before drafting's planner or editor calls, the editor payload is sized. Optional
policy excerpts are removed as needed; complete files and mandatory instructions
are never truncated. If required input cannot fit, the request stops with a clear
413. No automatic split across independent edits is performed; the caller must
agree a narrower scope or choose a budget/provider supporting the necessary input.
The final transport checks the actual serialized body again before sending.

| HTTP / detail.code | Meaning |
| --- | --- |
| 413 / input_budget_exceeded | Required input exceeds the configured local budget |
| 413 / provider_payload_too_large | Provider rejected size/token allowance despite local preflight |
| 429 / provider_rate_limited | Provider rate limit or quota response |
| 502 / provider_error | Other upstream HTTP error |

Errors include safe request size and numeric provider status. A numeric Retry-After
header is exposed as retry_after_seconds. Raw error bodies, credentials and endpoint
URLs are not returned. No automatic provider retries are introduced. Optional
excerpts are not automatically reduced after an upstream rejection; lower the
budget for a subsequent request or narrow its agreed scope.

input_summary on a successful draft records request_bytes, max_input_bytes,
editable_files and policy_excerpts_sent. No secrets or full sources are placed in
that summary. The baseline, render snapshot, verification checks, and preview apply
workflow are unchanged.

## Existing saved analysis and local update

Existing saved analysis records are supported without migration: targets are
resolved directly from proposed_changes. You can retry a failed draft with the
same change_id if the original page sources still match the saved baseline. No
failed provider call creates a successful draft or an applied preview.

After merging, preserve local commits with git fetch origin and git merge origin/main.
Then rebuild the rendered API image, preserving its data volume:

```sh
docker compose -f compose.yaml -f compose.rendered.yaml up -d --build --force-recreate impact
```

Expected API version: 0.7.1. Keep the user's existing .env/provider configuration.
No budget change is required to obtain the default; optionally set the variable
in private .env for the provider being used. Never overwrite local Groq changes
or discard them during merge conflict resolution.

## Validation

85 Python tests cover target scoping with/without contracts, multi-page proposals,
legacy saved reports, full rules/source preservation, unchanged saved baselines,
out-of-scope rejection, optional-excerpt reduction, required-input refusal before
model calls, actual UTF-8 wire size, and sanitized 413/429 mapping. Existing source,
HTTP workflow and rendered-staging regressions remain included.

A reconstruction using the user's supplied analysis for the three-page
pricing/design request measured 12428 serialized editor bytes with six policy
excerpts, versus at least 27891 bytes for the previous all-page/full-report shape.
This comparison excludes additional old planner/related-source context and uses
the saved original request as the draft description. Exact user draft size depends
on their description, provider model name and configuration.

No live provider key was used and no claim is made that the user's specific
provider limit has been reproduced or eliminated. Provider behavior is mocked;
request construction, scope enforcement and the HTTP workflow execute locally.
