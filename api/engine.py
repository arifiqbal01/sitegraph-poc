"""Read-only, fixture-scoped change impact analysis. AI enriches but never verifies evidence."""
import json
import os
from html.parser import HTMLParser
from pathlib import Path
from urllib import request
ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "demo-site" / "src" / "pages"
KNOWLEDGE = ROOT / "knowledge"
class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith("/") and not href.startswith("//"):
                self.links.append(href.split("#")[0].split("?")[0])
def pages(folder=SITE):
    result = {}
    for f in sorted(folder.rglob("*.astro")):
        rel = f.relative_to(folder).with_suffix("")
        route = "/" + str(rel).replace("index", "").strip("/")
        route = route.rstrip("/") or "/"
        result[route] = {"file": str(f.relative_to(ROOT)), "text": f.read_text()}
    return result
def links(text):
    p = Links()
    p.feed(text)
    return sorted(set(p.links))
def matches(text, term):
    return [i for i, line in enumerate(text.splitlines(), 1) if term.lower() in line.lower()]
def categories(p):
    q = (p.get("description", "") + " " + p.get("type", "")).lower()
    found = []
    for label, tokens in {"pricing": ["price", "pricing", "plan", "billing"], "navigation": ["navigation", "menu", "link", "seo", "route"], "accessibility": ["design", "color", "contrast", "layout", "button", "form", "accessibility", "cta"]}.items():
        if any(token in q for token in tokens):
            found.append(label)
    return found or ["general"]
def model_advice(proposal, evidence):
    key = os.environ.get("LLM_API_KEY")
    if not key:
        return {"mode": "deterministic", "note": "Optional AI not configured"}
    endpoint = os.environ.get("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    if not endpoint.startswith("https://"):
        return {"mode": "error", "note": "HTTPS required"}
    payload = {"model": os.environ.get("LLM_MODEL", "gpt-4o-mini"), "temperature": 0, "messages": [
        {"role": "system", "content": "You are a cautious change impact analyst. Explain relevant risks concisely. Never claim verification without evidence. Max 120 words."},
        {"role": "user", "content": json.dumps({"proposal": proposal, "evidence": evidence})[:12000]}]}
    try:
        req = request.Request(endpoint, json.dumps(payload).encode(), {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with request.urlopen(req, timeout=20) as response:
            return {"mode": "live", "advice": json.load(response)["choices"][0]["message"]["content"]}
    except Exception as exc:
        return {"mode": "unavailable", "note": "AI unavailable (" + type(exc).__name__ + "); deterministic evidence preserved"}
def analyze(proposal, with_ai=False):
    term = proposal.get("entity", "Starter")
    affected = []
    for route, p in pages().items():
        lines = matches(p["text"], term)
        if lines:
            affected.append({"route": route, "file": p["file"], "lines": lines, "basis": "text match"})
    knowledge = [{"file": str(f.relative_to(ROOT)), "lines": matches(f.read_text(), term)}
                 for f in KNOWLEDGE.rglob("*.md") if matches(f.read_text(), term)]
    types = categories(proposal)
    checks = []
    if "pricing" in types:
        checks.append("Verify plan, currency, billing period and authoritative pricing across relevant routes.")
    if "navigation" in types:
        checks.append("Inspect changed internal links and destinations.")
    if "accessibility" in types:
        checks.append("Use targeted rendered accessibility checks for changed UI.")
    report = {"checkpoint": "pre_implementation", "proposal": proposal, "analysis_categories": types,
              "related_pages": affected, "related_knowledge": knowledge, "recommended_checks": checks,
              "uncertainty": ["Matching text does not establish entity identity.", "Dynamic content may be missed."], "read_only": True}
    if with_ai:
        report["model"] = model_advice(proposal, report)
    return report
def verify(proposal, with_ai=False):
    baseline = pages()
    candidate = pages(ROOT / "scenarios" / proposal.get("scenario", "pricing-incomplete") / "pages")
    types, findings, changed = categories(proposal), [], []
    term, old, new = proposal.get("entity", "Starter"), proposal.get("old_value"), proposal.get("new_value")
    for route, base in baseline.items():
        current = candidate.get(route, base)
        if base["text"] != current["text"]:
            changed.append(route)
        if "pricing" in types and old and new and matches(base["text"], term) and old in base["text"]:
            if old in current["text"]:
                findings.append({"category": "business_consistency", "severity": "high", "route": route,
                                 "file": current["file"], "status": "needs_review", "evidence": old + " still appears"})
            elif new in current["text"]:
                findings.append({"category": "business_consistency", "severity": "info", "route": route,
                                 "file": current["file"], "status": "updated", "evidence": new + " observed"})
        if "navigation" in types:
            for link in sorted(set(links(base["text"])) - set(links(current["text"]))):
                findings.append({"category": "navigation", "severity": "medium", "route": route,
                                 "file": current["file"], "status": "needs_review", "evidence": "Removed internal link: " + link})
    if "accessibility" in types:
        findings.append({"category": "accessibility", "severity": "info", "status": "not_assessed",
                         "evidence": "Browser/axe verification not yet implemented."})
    report = {"checkpoint": "pre_publish", "proposal": proposal, "changed_routes": changed, "analysis_categories": types,
              "findings": findings, "decision": "review_required" if any(f["status"] == "needs_review" for f in findings) else "no_detected_blockers",
              "read_only": True, "limitations": ["Static fixtures only; external checkout and dynamic content not verified.", "No SEO ranking or legal compliance claims."]}
    if with_ai:
        report["model"] = model_advice(proposal, report)
    return report
