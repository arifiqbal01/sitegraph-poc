# SiteGraph POC — agent-proposal change impact intelligence

SiteGraph is a read-only impact checkpoint around an AI website editing agent. The fictional Northstar Astro site and Groq-backed demo editor simulate an external agent; **this is not a live Sherpa integration**.

## Run

```bash
docker compose up -d --build --force-recreate
```

API: http://localhost:8000/docs · Demo: http://localhost:4321

Set `LLM_API_KEY`, `LLM_MODEL`, `LLM_API_URL` in a private `.env` to enable the optional demo agent. Never commit credentials.

## Connected workflow (v0.3)

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

The source graph is persisted in SQLite. Reindexing reads files to compare hashes but reparses only changed files. Pre-impact checks use literal references and static internal links, not semantic equivalence or a full dependency resolver. Business knowledge is limited to the included local markdown files. Draft editing supports existing Astro pages only, so knowledge changes are correctly reported as unresolved when applicable. No browser/axe checks, live route checks, runtime SEO validation, Astro build validation, or actual analytics integration are implemented. The preview is **not served** by Astro. Verification does not prove a change achieved its business goal; it reports source-level evidence only. Existing `/ai/plan` remains a demo agent tool, not SiteGraph's impact authority.

Run tests locally with `python -m unittest discover -s tests -v`.
