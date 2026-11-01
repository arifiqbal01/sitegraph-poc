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
def draft(description):
    graph.rebuild()
    indexed = graph.snapshot()
    files = {str(p.relative_to(ROOT)):p.read_text() for p in sorted((SOURCE/"pages").rglob("*.astro"))}
    if len(files) > MAX_FILES:
        raise ValueError("Demo exceeds bounded edit scope")
    terms = description.split()
    matches = graph.search(next((x for x in terms if len(x)>4),"Starter"))
    planning = ai.plan(description,indexed,matches)
    context = {"plan":planning,"related_sources":graph.search(planning.get("entity","Starter"))}
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
    (workspace/"proposal.json").write_text(json.dumps({"description":description,"plan":planning,"edits":prepared},indent=2))
    return {"draft_id":id,"status":"pending_review","plan":planning,
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
