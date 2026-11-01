"""Isolated preview changes, explicit approval; never mutate original demo sources."""
import difflib
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from . import graph, ai
ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "demo-site" / "src"
WORKSPACES = Path("/app/data/workspaces") if Path("/app").exists() else ROOT / ".sitegraph" / "workspaces"
MAX_FILES = 12
MAX_SIZE = 50000
def allowed(path):
    if not re.fullmatch(r"demo-site/src/pages/[a-zA-Z0-9_./-]+\.astro",path) or ".." in Path(path).parts:
        raise ValueError("Only demo-site/src/pages/*.astro files can be edited")
    actual = (ROOT / path).resolve()
    if not actual.is_relative_to((SOURCE / "pages").resolve()) or not actual.is_file():
        raise ValueError("File is not an existing demo page: " + path)
    return actual
def draft(description, change_id=None, implementation_contract=None):
    graph.rebuild()
    indexed = graph.snapshot()
    files = {str(p.relative_to(ROOT)):p.read_text() for p in sorted((SOURCE/"pages").rglob("*.astro"))}
    if len(files) > MAX_FILES:
        raise ValueError("Demo exceeds bounded edit scope")
    terms = description.split()
    matches = graph.search(next((x for x in terms if len(x)>4),"Starter"))
    context = {}
    bound_contract = None
    if implementation_contract is not None and not change_id:
        raise ValueError("A contract requires a change_id and saved baseline")
    if change_id:
        from . import checkpoints
        record = checkpoints.load(change_id)
        impact = record["report"]
        if any(record["baseline"].get(path) != content for path, content in files.items()) or any(path.startswith("demo-site/src/pages/") and path not in files for path in record["baseline"]):
            raise ValueError("Source changed since analysis; create a new analysis")
        saved_contract = impact.get("implementation_contract")
        if saved_contract is not None and implementation_contract is not None and saved_contract != implementation_contract:
            raise ValueError("Cannot override the analysis contract; create a new analysis")
        bound_contract = checkpoints.validate_contract(saved_contract if saved_contract is not None else implementation_contract, record["baseline"], impact["proposed_changes"])
        if bound_contract:
            context["implementation_contract"] = bound_contract
        context["mandatory_impact_context"] = impact
        context["instruction"] = "For navigation href changes, edit only explicitly targeted pages; related links are context, not mandatory edits. The explicit implementation_contract, if supplied, defines edit scope and preservation requirements. Related pricing references need updates only when a value change is explicitly authorized. Do not change prices or knowledge policy for a presentation-only request. Disclose unsupported knowledge edits."

    planning = ai.plan(description,indexed,matches)
    context.update(plan=planning, related_sources=graph.search(planning.get("entity", "Starter")))
    result = ai.propose_edits(description,files,context)
    edits = result.get("edits",[])
    if not isinstance(edits,list) or len(edits)>MAX_FILES:
        raise ValueError("Invalid number of proposed edits")
    if not edits:
        raise ValueError("Model proposed no edits")
    prepared = []
    seen = set()
    for edit in edits:
        path = edit["path"]
        target = allowed(path)
        content = edit["content"]
        if path in seen or not isinstance(content,str) or not content.strip() or len(content)>MAX_SIZE:
            raise ValueError("Invalid or duplicate proposed edit")
        if not content.lstrip().startswith("---") or "</" not in content:
            raise ValueError("Proposed Astro content failed basic sanity checks")
        seen.add(path)
        before = target.read_text()
        prepared.append({"path":path,"before":before,"after":content,"reason":edit.get("reason",""),
                         "diff":"".join(difflib.unified_diff(before.splitlines(True),content.splitlines(True),fromfile="before/"+path,tofile="after/"+path))})
    id = uuid.uuid4().hex
    workspace = WORKSPACES / id
    workspace.mkdir(parents=True)
    (workspace/"proposal.json").write_text(json.dumps({"description":description,"change_id":change_id,"implementation_contract":bound_contract,"plan":planning,"edits":prepared},indent=2))
    return {"draft_id":id,"status":"pending_review","change_id":change_id,"plan":planning,
            "implementation_contract":bound_contract,
            "changes":[{"path":e["path"],"reason":e["reason"],"diff":e["diff"]} for e in prepared],
            "note":"No source files modified. Explicit apply is required."}
def apply(id):
    if not re.fullmatch("[a-f0-9]{32}",id):
        raise ValueError("Invalid draft ID")
    file = WORKSPACES/id/"proposal.json"
    if not file.is_file():
        raise ValueError("Unknown draft")
    data = json.loads(file.read_text())
    preview = WORKSPACES/id/"preview"/"pages"
    if preview.exists():
        raise ValueError("Draft already applied")
    # Detect concurrent changes: don't apply stale proposals.
    for edit in data["edits"]:
        if allowed(edit["path"]).read_text() != edit["before"]:
            raise ValueError("Source changed since draft; regenerate")
    shutil.copytree(SOURCE/"pages",preview)
    for edit in data["edits"]:
        relative = allowed(edit["path"]).relative_to(SOURCE/"pages")
        (preview/relative).write_text(edit["after"])
    return {"draft_id":id,"status":"applied_to_isolated_preview","preview_path":str(preview),
            "changed_files":[e["path"] for e in data["edits"]],
            "note":"Original demo-site source remains untouched; preview is not published."}
