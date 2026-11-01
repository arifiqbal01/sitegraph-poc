# SiteGraph POC — Change Impact Intelligence for AI website agents

Read-only, two-checkpoint demonstration of a **possible native Sherpa AI enhancement**. The fixture is fictional and does not integrate with Sherpa.

## Docker

```bash
docker compose up --build
```

Astro demo: http://localhost:4321 · API docs: http://localhost:8000/docs

Use `POST /impact/analyze` (agent-facing) and `POST /impact/verify` (human-facing) with:

```json
{"description":"Reduce Starter plan price from $29.90 to $19.90 per month","type":"pricing","entity":"Starter","old_value":"$29.90","new_value":"$19.90","scenario":"pricing-incomplete","use_ai":false}
```

Pre-change analysis finds homepage, pricing page, FAQ and company knowledge as relevant context. Candidate changes homepage and pricing, but not FAQ, so post-change verification requests review. Set scenario to `pricing-complete` for a pass; use scenario `navigation-removed` and description "Simplify services navigation" for link removal detection.

## Optional live AI

Copy `.env.example` to `.env`, enter `LLM_API_KEY` and set `"use_ai":true` in requests. Never commit the key. AI adds concise interpretation; source evidence and findings remain deterministic.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Honest limitations

Static Astro fixture and heuristic business entity matches only; no full AST dependency resolution, no external billing or document integrations, no browser/axe accessibility engine yet. Design proposals are classified for accessibility checks, but these are reported **not assessed**, not falsely passed. No legal compliance certification or SEO ranking predictions. The tool is read-only; fixture candidate edits are prewritten.

The goal is to demonstrate **agent impact context before implementation** and **evidence-based human review before publishing**, not create a separate Sherpa competitor.
