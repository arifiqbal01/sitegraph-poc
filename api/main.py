from fastapi import FastAPI
from pydantic import BaseModel
from .engine import analyze, verify
app = FastAPI(title="SiteGraph Change Impact POC", version="0.1.0")
class Proposal(BaseModel):
    description: str
    type: str = ""
    entity: str = "Starter"
    old_value: str | None = None
    new_value: str | None = None
    scenario: str = "pricing-incomplete"
    use_ai: bool = False
@app.get("/health")
def health():
    return {"status": "ok", "read_only": True}
@app.post("/impact/analyze")
def impact_analyze(proposal: Proposal):
    return analyze(proposal.model_dump(), with_ai=proposal.use_ai)
@app.post("/impact/verify")
def impact_verify(proposal: Proposal):
    return verify(proposal.model_dump(), with_ai=proposal.use_ai)
