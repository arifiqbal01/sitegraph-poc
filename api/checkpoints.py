"""Agent-proposal impact checkpoints. Static evidence only; no production writes."""
import json
import re
import uuid
from pathlib import Path
from . import graph, contracts, investigations
from .engine import links

ROOT = Path(__file__).resolve().parent.parent
STORE = Path("/app/data/changes") if Path("/app").exists() else ROOT / ".sitegraph" / "changes"
PAGES = ROOT / "demo-site" / "src" / "pages"
KNOWLEDGE = ROOT / "knowledge"

def _files():
    return {str(p.relative_to(ROOT)): p.read_text() for p in sorted(list(PAGES.rglob("*.astro")) + list(KNOWLEDGE.rglob("*.md")))}

def _route(path):
    rel = Path(path).relative_to("demo-site/src/pages").with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "index":
        parts.pop()
    return "/" + "/".join(parts)

def _targets(proposal):
    return [x for x in proposal.get("proposed_changes", []) if isinstance(x, dict)]


def _is_navigation(change):
    return str(change.get("field", "")).lower() in ("internal_link", "href", "link", "navigation_link")

def _normalized_href(value):
    return str(value).split("#", 1)[0].split("?", 1)[0].rstrip("/") or "/"

def _target_path(target, baseline):
    target = str(target or "").strip()
    if target in baseline:
        return target
    for path in baseline:
        if path.startswith("demo-site/src/pages/") and _route(path) == target:
            return path
    return None

def _nav_refs(content, href):
    # Extract exact internal href attributes, avoiding prefix matches such as
    # /services appearing inside /services/seo.
    expected = _normalized_href(href)
    return [n for n, line in enumerate(content.splitlines(), 1)
            if any(_normalized_href(dest) == expected
                   for dest in re.findall(r"""\bhref\s*=\s*["'](/[^"'<>\s]*)["']""", line))]

def _typed_changes(changes):
    return [c for c in changes if _is_navigation(c) and c.get("old_value") and c.get("new_value")]

def validate_contract(value, baseline, changes):
    contract = contracts.validate(value, baseline)
    if contract:
        for rule in contract['checks']:
            if rule['kind'] in contracts.OUTCOMES:
                index = rule.get('change_index', 0)
                if index >= len(changes) or _target_path(changes[index].get('target'), baseline) != rule['file']:
                    raise ValueError('Contract outcome must match its proposed change_index target')
    return contract

def analyze(proposal):
    if not _targets(proposal):
        raise ValueError("proposed_changes must contain at least one agent-proposed action")
    graph.rebuild()
    baseline = _files()
    changes = _targets(proposal)
    contract = validate_contract(proposal.get("implementation_contract"), baseline, changes)
    terms = sorted({str(v).strip() for c in changes for k in ("old_value", "entity") for v in [c.get(k)] if v and len(str(v).strip()) >= 3}, key=len, reverse=True)
    explicit = {str(c.get("target", "")).strip() for c in changes}
    navigation = _typed_changes(changes)
    matches = []
    for path, content in baseline.items():
        route = _route(path) if path.startswith("demo-site/src/pages/") else None
        lines = sorted({n for term in terms if not any(str(c.get("old_value")) == term for c in navigation) for n, line in enumerate(content.splitlines(), 1) if term.casefold() in line.casefold()} | {n for c in navigation for n in _nav_refs(content, c["old_value"])})
        if lines or path in explicit or route in explicit:
            matches.append({"file": path, "route": route, "kind": "page" if route is not None else "knowledge", "lines": lines, "basis": "literal evidence" if lines else "agent target"})
    routes = {x["route"] for x in matches if x["route"] is not None}
    intended = sorted({p for c in changes for p in [_target_path(c.get("target"), baseline)] if p})
    related = sorted(x["route"] for x in matches if x["route"] is not None and x["file"] not in intended)
    incoming = []
    for path, content in baseline.items():
        if not path.endswith(".astro"):
            continue
        for dest in links(content):
            if dest in routes:
                incoming.append({"source_route": _route(path), "destination": dest, "file": path})
    categories = set()
    all_text = json.dumps(changes).lower()
    if any(t in all_text for t in ("price", "pricing", "billing", "plan")): categories.add("business_consistency")
    if any(t in all_text for t in ("link", "route", "navigation", "menu", "redirect", "404")): categories.update(("navigation", "seo"))
    if any(t in all_text for t in ("button", "form", "layout", "cta", "design")): categories.add("accessibility")
    checks = ["Check confirmed references for incomplete edits", "Review unexpected file changes"]
    if "navigation" in categories: checks += ["Check internal destinations and inbound links", "Review redirects and canonical URLs"]
    if "accessibility" in categories: checks += ["Run rendered accessibility checks (not implemented in POC)"]
    change_id = uuid.uuid4().hex
    report = {"change_id": change_id, "checkpoint": "pre_implementation", "trigger": proposal.get("trigger", "agent_discovery"),
              "agent": proposal.get("agent", "external_agent"), "original_request": proposal.get("original_request"),
              "proposed_changes": changes, "confirmed_references": matches, "affected_routes": sorted(routes),
              "incoming_links": incoming, "intended_edit_files": intended, "related_routes": related, "analysis_categories": sorted(categories),
              "recommended_checks": checks, "read_only": True,
              "limitations": ["Literal source matching is not semantic entity resolution.", "Runtime, analytics, accessibility and external systems have not been verified.", "Knowledge access is limited to locally supplied demo files."]}
    from .reasoning import implementation_brief
    report["implementation_contract"] = contract
    report["impact_investigations"] = investigations.plan(proposal, matches)
    report["implementation_brief"] = implementation_brief(proposal, baseline)
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / (change_id + ".json")).write_text(json.dumps({"report": report, "baseline": baseline}, indent=2))
    return report

def load(change_id):
    if not re.fullmatch(r"[0-9a-f]{32}", change_id):
        raise ValueError("Invalid change_id")
    path = STORE / (change_id + ".json")
    if not path.is_file():
        raise ValueError("Unknown change_id")
    return json.loads(path.read_text())

def verify(change_id, draft_id):
    record = load(change_id)
    before = record["baseline"]
    report = record["report"]
    from .workspace import WORKSPACES
    if not re.fullmatch(r"[0-9a-f]{32}", draft_id):
        raise ValueError("Invalid draft_id")
    proposal_file = WORKSPACES / draft_id / "proposal.json"
    preview = WORKSPACES / draft_id / "preview" / "pages"
    if not proposal_file.is_file() or not preview.is_dir():
        raise ValueError("Draft must be applied to isolated preview before verification")
    draft = json.loads(proposal_file.read_text())
    if draft.get("change_id") != change_id:
        raise ValueError("Draft does not belong to this impact analysis")
    after = dict(before)
    for path in before:
        if path.startswith("demo-site/src/pages/"):
            relative = Path(path).relative_to("demo-site/src/pages")
            candidate = preview / relative
            if candidate.is_file():
                after[path] = candidate.read_text()
            else:
                after[path] = ""
    missing_pages = [p for p in before if p.startswith("demo-site/src/pages/")
                     and not (preview / Path(p).relative_to("demo-site/src/pages")).is_file()]
    for candidate in preview.rglob("*.astro"):
        path = "demo-site/src/pages/" + candidate.relative_to(preview).as_posix()
        if path not in before:
            after[path] = candidate.read_text()
    changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    saved_contract = report.get("implementation_contract")
    draft_contract = draft.get("implementation_contract")
    if saved_contract is not None and draft_contract is not None and saved_contract != draft_contract:
        raise ValueError("Draft contract differs from immutable analysis contract")
    contract = validate_contract(saved_contract if saved_contract is not None else draft_contract, before, report["proposed_changes"])
    contract_checks = contracts.evaluate(contract, before, after)
    scope_checks = contracts.scope_checks(contract, before, after)
    changes = report["proposed_changes"]
    nav_changes = _typed_changes(changes)
    expected = {item["file"] for item in report["confirmed_references"]
                if any(not _is_navigation(c) and c.get("old_value")
                       and str(c["old_value"]) in before[item["file"]] for c in changes)}
    intended = {_target_path(c.get("target"), before) for c in changes}
    intended.discard(None)
    checks = []
    destination_checks = []
    authorized_removals = set()
    for c in nav_changes:
        target = _target_path(c.get("target"), before)
        old_href, new_href = _normalized_href(c["old_value"]), _normalized_href(c["new_value"])
        if target is None:
            checks.append({"file": str(c.get("target", "")), "route": None, "status": "needs_review", "detail": "Target route not found"})
            destination_checks.append({"destination": new_href, "status": "not_assessed", "detail": "Target route not found"})
            continue
        original_refs = _nav_refs(before[target], old_href)
        current_old = _nav_refs(after[target], old_href)
        current_new = _nav_refs(after[target], new_href)
        before_new = _nav_refs(before[target], new_href)
        replaced = bool(original_refs) and len(current_old) < len(original_refs) and len(current_new) > len(before_new)
        if replaced:
            authorized_removals.add((target, old_href))
        if not original_refs:
            status, detail = "needs_review", "Expected original href not found on target"
        elif current_old:
            status, detail = "missed", "Original href remains on intended target"
        elif replaced:
            status, detail = "updated", "Expected href replacement observed"
        else:
            status, detail = "needs_review", "Original href removed but replacement not confirmed"
        checks.append({"file": target, "route": _route(target), "status": status, "detail": detail})
        known_routes = {_route(p) for p in after if p.startswith("demo-site/src/pages/") and p not in missing_pages}
        destination_checks.append({"destination": new_href, "status": "exists" if new_href in known_routes else "missing",
                                   "detail": "Static Astro page route lookup; runtime routing not tested"})
    # Explicit, locator-bound href changes are also authorized replacements.
    for assertion in contract_checks:
        if assertion.get("attribute") != "href" or not assertion.get("outcome_change"):
            continue
        evidence = assertion["evidence"]
        old, new = evidence.get("before"), evidence.get("after")
        if isinstance(old, str) and old.startswith("/"):
            authorized_removals.add((assertion["file"], _normalized_href(old)))
        if isinstance(new, str) and new.startswith("/"):
            known_routes = {_route(p) for p in after if p.startswith("demo-site/src/pages/") and p not in missing_pages}
            destination_checks.append({"destination": _normalized_href(new), "status": "exists" if _normalized_href(new) in known_routes else "missing",
                                       "detail": "Contract href checked against static page routes; runtime not tested"})
    for item in report["confirmed_references"]:
        path = item["file"]
        original = before[path]
        current = after[path]
        relevant = [c for c in changes if not _is_navigation(c) and c.get("old_value") and c.get("new_value")
                    and str(c["old_value"]) in original]
        if relevant:
            remaining = [str(c["old_value"]) for c in relevant if str(c["old_value"]) in current]
            new_seen = all(str(c["new_value"]) in current for c in relevant)
            status = "missed" if remaining else ("updated" if new_seen else "needs_review")
            detail = "Old value remains" if remaining else ("Replacement observed" if new_seen else "Old value removed; replacement not confirmed")
            checks.append({"file": path, "route": item["route"], "status": status, "detail": detail})
        elif not nav_changes:
            checks.append({"file": path, "route": item["route"],
                           "status": "changed" if path in changed else "not_assessed",
                           "detail": "No literal old/new pair to verify"})
    unexpected = sorted(set(changed) - (set(contract["allowed_edit_files"]) if contract else expected | intended))
    outcome_checks = []
    for index, change in enumerate(changes):
        target = _target_path(change.get("target"), before)
        matching_contract = [c for c in contract_checks if c["file"] == target and c.get("outcome_change") and c.get("change_index", 0) == index]
        literal_pair = bool(change.get("old_value") and change.get("new_value") and change["old_value"] != change["new_value"])
        literal_verified = False
        if target and literal_pair:
            if _is_navigation(change):
                old, new = change["old_value"], change["new_value"]
                literal_verified = (bool(_nav_refs(before[target], old)) and not _nav_refs(after[target], old)
                                    and len(_nav_refs(after[target], new)) > len(_nav_refs(before[target], new)))
            else:
                old, new = str(change["old_value"]), str(change["new_value"])
                literal_verified = old in before[target] and old not in after[target] and new in after[target]
        field = str(change.get("field", "")).lower()
        runtime_required = any(term in field for term in ("contrast", "keyboard", "accessibility_compliance", "ranking", "indexability", "fact_accuracy", "checkout", "approval", "conversion", "performance"))
        assessed = bool(target and (literal_verified or matching_contract) and not runtime_required)
        outcome_checks.append({"change_index": index, "target": change.get("target"),
                               "status": "passed" if assessed else "not_assessed",
                               "detail": "Explicit source outcome observed" if assessed else ("Requested outcome needs runtime or external evidence; source assertions are insufficient" if runtime_required else "No verified explicit outcome for proposed change; changed-file presence is insufficient")})
    inspection = investigations.verify(report, before, after, changed, contract_checks, scope_checks)
    coverage_gaps = [x for x in outcome_checks if x["status"] != "passed"]
    failed_contract = [x for x in contract_checks if x["status"] != "passed"]
    unresolved_scope = [x for x in scope_checks if x["status"] != "passed"]
    source_regressions = [x for x in inspection if x["status"] == "review_required"]
    removed_links = []
    for path in changed:
        if path.endswith(".astro"):
            for dest in sorted(set(links(before.get(path, ""))) - set(links(after.get(path, "")))):
                if (path, _normalized_href(dest)) not in authorized_removals:
                    removed_links.append({"file": path, "removed_destination": dest, "status": "needs_review"})
    unresolved = [x for x in checks if x["status"] in ("missed", "needs_review")]
    missing_destinations = [x for x in destination_checks if x["status"] == "missing"]
    decision = "review_required" if unresolved or unexpected or removed_links or missing_destinations or coverage_gaps or failed_contract or source_regressions or missing_pages or unresolved_scope else "no_detected_blockers"
    return {"change_id": change_id, "draft_id": draft_id, "checkpoint": "pre_publish",
            "original_proposal": report["proposed_changes"], "affected_routes": report["affected_routes"],
            "changed_files": changed, "changed_routes": sorted(_route(p) for p in changed if p.endswith(".astro")),
            "reference_checks": checks, "missed_references": unresolved, "destination_checks": destination_checks,
            "related_routes_unchanged": sorted(x["route"] for x in report["confirmed_references"] if x["route"] is not None and x["file"] not in changed and x["file"] not in intended),
            "implementation_contract": contract, "contract_checks": contract_checks, "scope_checks": scope_checks,
            "outcome_checks": outcome_checks, "investigation_results": inspection,
            "missing_preview_files": missing_pages,
            "human_report": {
                "decision": decision,
                "verified": [c["id"] for c in contract_checks if c["status"] == "passed"],
                "requires_review": [c["id"] for c in failed_contract] + [c["detail"] for c in coverage_gaps]
                                   + ["Unresolved reference: " + c["file"] for c in unresolved]
                                   + ["Unexpected edit: " + p for p in unexpected]
                                   + ["Missing preview file: " + p for p in missing_pages]
                                   + ["Out-of-contract edit: " + c["file"] for c in unresolved_scope]
                                   + ["Missing destination: " + c["destination"] for c in missing_destinations]
                                   + ["Removed link: " + c["removed_destination"] for c in removed_links]
                                   + [e["detail"] for result in source_regressions for e in result["evidence"]],
                "not_assessed": [x["detail"] for x in inspection if x["status"] in ("not_run", "not_assessed")],
                "scope": "Source evidence only; business approval and publication remain human decisions."
            },
            "unexpected_changes": unexpected,
            "removed_internal_links": removed_links, "decision": decision, "read_only": True,
            "summary": f"{len(changed)} files modified; {len(unresolved)} unresolved references; {len(unexpected)} unexpected files; {len(removed_links)} unapproved removed internal links; {len(missing_destinations)} missing destinations; {len(coverage_gaps)} unassessed outcomes; {len(failed_contract)} unresolved contract checks; {len(source_regressions)} investigation groups requiring review; {len(missing_pages)} missing preview files.",
            "limitations": ["Static source checks only; browser behavior, accessibility, live routes, SEO outcomes and external knowledge are not verified.", "No publication performed."]}
