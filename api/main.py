from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .engine import analyze, verify
from . import graph, workspace, ai
app = FastAPI(title="SiteGraph Change Impact POC", version="0.2.0")
class Proposal(BaseModel):
    description: str
    type: str = ""
    entity: str = "Starter"
    old_value: str | None = None
    new_value: str | None = None
    scenario: str = "pricing-incomplete"
    use_ai: bool = False
class Request(BaseModel):
    description: str
class ApplyRequest(BaseModel):
    draft_id: str
@app.get("/health")
def health():
    return {"status":"ok","read_only_core":True,"ai_configured":bool(__import__("os").getenv("LLM_API_KEY"))}
@app.post("/graph/reindex")
def reindex():
    return graph.rebuild()
@app.get("/graph")
def get_graph():
    graph.rebuild()
    return graph.snapshot()
@app.post("/impact/analyze")
def impact_analyze(proposal:Proposal):
    return analyze(proposal.model_dump(),with_ai=proposal.use_ai)
@app.post("/impact/verify")
def impact_verify(proposal:Proposal):
    return verify(proposal.model_dump(),with_ai=proposal.use_ai)
@app.post("/ai/plan")
def ai_plan(body:Request):
    try:
        graph.rebuild()
        indexed = graph.snapshot()
        result = ai.plan(body.description,indexed,[])
        terms = result.get("search_terms",[])
        evidence = {term:graph.search(term) for term in terms[:5] if isinstance(term,str) and term.strip()}
        return {"plan":result,"evidence":evidence,"graph":graph.rebuild()}
    except Exception as exc:
        raise HTTPException(422,detail=str(exc))
@app.post("/ai/draft")
def ai_draft(body:Request):
    try:
        return workspace.draft(body.description)
    except Exception as exc:
        raise HTTPException(422,detail=str(exc))
@app.post("/ai/apply")
def ai_apply(body:ApplyRequest):
    try:
        return workspace.apply(body.draft_id)
    except Exception as exc:
        raise HTTPException(422,detail=str(exc))
