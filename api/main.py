from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from . import graph, workspace, ai, checkpoints
app = FastAPI(title="SiteGraph Change Impact POC", version="0.6.0")

class AgentProposal(BaseModel):
    agent: str = "sherpa-simulator"
    trigger: str = "agent_discovery"
    original_request: str | None = None
    use_ai: bool = False
    implementation_contract: dict[str, Any] | None = None
    proposed_changes: list[dict[str, Any]] = Field(min_length=1)

class Verification(BaseModel):
    change_id: str
    draft_id: str

class Request(BaseModel):
    description: str
    change_id: str | None = None
    implementation_contract: dict[str, Any] | None = None

class ApplyRequest(BaseModel):
    draft_id: str

@app.get("/health")
def health():
    return {"status": "ok", "read_only_core": True, "ai_configured": bool(__import__("os").getenv("LLM_API_KEY"))}

@app.post("/graph/reindex")
def reindex():
    return graph.rebuild()

@app.get("/graph")
def get_graph():
    graph.rebuild()
    return graph.snapshot()

@app.post("/impact/analyze")
def impact_analyze(body: AgentProposal):
    try:
        return checkpoints.analyze(body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))

@app.post("/impact/verify")
def impact_verify(body: Verification):
    try:
        return checkpoints.verify(body.change_id, body.draft_id)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))

@app.post("/ai/plan")
def ai_plan(body: Request):
    try:
        graph.rebuild()
        indexed = graph.snapshot()
        result = ai.plan(body.description, indexed, [])
        terms = result.get("search_terms", [])
        evidence = {term: graph.search(term) for term in terms[:5] if isinstance(term, str) and term.strip()}
        return {"plan": result, "evidence": evidence, "graph": graph.rebuild(), "note": "Demo agent planner, not authoritative impact analysis"}
    except Exception as exc:
        raise HTTPException(422, detail=str(exc))

@app.post("/ai/draft")
def ai_draft(body: Request):
    try:
        return workspace.draft(body.description, change_id=body.change_id, implementation_contract=body.implementation_contract)
    except Exception as exc:
        raise HTTPException(422, detail=str(exc))

@app.post("/ai/apply")
def ai_apply(body: ApplyRequest):
    try:
        return workspace.apply(body.draft_id)
    except Exception as exc:
        raise HTTPException(422, detail=str(exc))
