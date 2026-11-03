"""Persistent incremental source graph. No third-party packages needed."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from html.parser import HTMLParser
ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "demo-site" / "src"
KNOWLEDGE = ROOT / "knowledge"
DB = Path("/app/data/sitegraph.sqlite") if Path("/app").exists() else ROOT / ".sitegraph" / "graph.sqlite"
class Extract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href", "").startswith("/"):
            self.links.append(attrs["href"].split("#")[0].split("?")[0])
def route(path):
    rel = path.relative_to(SITE / "pages").with_suffix("")
    result = "/" + str(rel).replace("index", "").strip("/")
    return result.rstrip("/") or "/"
def connection():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS nodes (path TEXT PRIMARY KEY, hash TEXT NOT NULL, route TEXT, kind TEXT, text TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS edges (source TEXT, target TEXT, relation TEXT, PRIMARY KEY(source,target,relation))")
    db.execute("CREATE INDEX IF NOT EXISTS edges_target ON edges(target)")
    return db
def source_files():
    return sorted(list(SITE.rglob("*.astro")) + list(KNOWLEDGE.rglob("*.md")) + list(KNOWLEDGE.rglob("*.json")))
def rebuild():
    """Reparse changed files only; delete removed nodes; retain index on disk."""
    db = connection()
    changed = []
    all_paths = set()
    for path in source_files():
        key = str(path.relative_to(ROOT))
        all_paths.add(key)
        content = path.read_text()
        digest = hashlib.sha256(content.encode()).hexdigest()
        previous = db.execute("SELECT hash FROM nodes WHERE path=?", (key,)).fetchone()
        if previous and previous[0] == digest:
            continue
        kind = "page" if path.suffix == ".astro" and "pages" in path.parts else ("knowledge" if path.suffix in {".md", ".json"} else "component")
        page_route = route(path) if kind == "page" else None
        db.execute("INSERT OR REPLACE INTO nodes VALUES(?,?,?,?,?)", (key,digest,page_route,kind,content))
        db.execute("DELETE FROM edges WHERE source=?", (key,))
        if kind == "page":
            parser = Extract()
            parser.feed(content)
            for dest in set(parser.links):
                db.execute("INSERT OR IGNORE INTO edges VALUES(?,?,?)", (key,dest,"links_to_route"))
        for imp in re.findall(r"""(?:from\s+|import\s*\()['\"]([^'\"]+)['\"]""", content):
            if imp.startswith("."):
                db.execute("INSERT OR IGNORE INTO edges VALUES(?,?,?)", (key,imp,"imports"))
        changed.append(key)
    for (key,) in db.execute("SELECT path FROM nodes").fetchall():
        if key not in all_paths:
            db.execute("DELETE FROM nodes WHERE path=?", (key,))
            db.execute("DELETE FROM edges WHERE source=?", (key,))
            changed.append(key)
    db.commit()
    count = db.execute("SELECT count(*) FROM nodes").fetchone()[0]
    edges = db.execute("SELECT count(*) FROM edges").fetchone()[0]
    db.close()
    return {"changed_files":changed,"indexed_files":count,"edges":edges,"strategy":"sha256 incremental reindex"}
def search(term, limit=30):
    db = connection()
    matches = []
    for path, page_route, kind, content in db.execute("SELECT path,route,kind,text FROM nodes"):
        lines = [n for n,line in enumerate(content.splitlines(),1) if term.casefold() in line.casefold()]
        if lines:
            matches.append({"file":path,"route":page_route,"kind":kind,"lines":lines[:10]})
        if len(matches) >= limit:
            break
    db.close()
    return matches
def snapshot():
    db = connection()
    nodes = [{"file":path,"route":route,"kind":kind} for path,route,kind in db.execute("SELECT path,route,kind FROM nodes")]
    edges = [{"source":a,"target":b,"relation":c} for a,b,c in db.execute("SELECT source,target,relation FROM edges")]
    db.close()
    return {"nodes":nodes,"edges":edges}
