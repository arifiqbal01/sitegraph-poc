from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from . import graph, workspace, ai, checkpoints, suggestions, workflow
app = FastAPI(title="SiteGraph Change Impact POC", version="0.8.0")

class AgentProposal(BaseModel):
    agent: str = "sherpa-simulator"
    trigger: str = "agent_discovery"
    original_request: str | None = None
    use_ai: bool = False
    implementation_contract: dict[str, Any] | None = None
    proposed_changes: list[dict[str, Any]] = Field(min_length=1)
    suggestion_context: dict[str, Any] | None = None

class Verification(BaseModel):
    change_id: str
    draft_id: str
    run_rendered: bool = False
    run_ai_review: bool = False

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
        return checkpoints.verify(body.change_id, body.draft_id, run_rendered=body.run_rendered, run_ai_review=body.run_ai_review)
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
    except ai.ModelRequestError as exc:
        raise HTTPException(exc.status_code, detail=exc.detail)
    except Exception as exc:
        raise HTTPException(422, detail=str(exc))

@app.post("/ai/draft")
def ai_draft(body: Request):
    try:
        return workspace.draft(body.description, change_id=body.change_id, implementation_contract=body.implementation_contract)
    except ai.ModelRequestError as exc:
        raise HTTPException(exc.status_code, detail=exc.detail)
    except Exception as exc:
        raise HTTPException(422, detail=str(exc))

@app.post("/ai/apply")
def ai_apply(body: ApplyRequest):
    try:
        return workspace.apply(body.draft_id)
    except Exception as exc:
        raise HTTPException(422, detail=str(exc))


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=6000)


class WorkflowRequest(PromptRequest):
    run_rendered: bool = True
    run_ai_review: bool = True


@app.post("/impact/propose")
def impact_propose(body: PromptRequest):
    try:
        return suggestions.propose(body.prompt)
    except ai.ModelRequestError as exc:
        raise HTTPException(exc.status_code, detail=exc.detail)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))


@app.post("/workflow/run")
def workflow_run(body: WorkflowRequest):
    try:
        return workflow.run(body.prompt, body.run_rendered, body.run_ai_review)
    except workflow.WorkflowFailure as exc:
        raise HTTPException(exc.status_code, detail=exc.record)


@app.get("/workflow/{workflow_id}")
def workflow_get(workflow_id: str):
    try:
        return workflow.load(workflow_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))
