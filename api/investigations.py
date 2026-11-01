"""Proposal-guided source investigations with explicit coverage boundaries."""
import json
from collections import Counter
from .source import SourceTree

DOMAINS = {
    'business': ('price', 'pricing', 'billing', 'plan', 'subscription', 'checkout', 'currency'),
    'facts': ('fact', 'claim', 'feature', 'team member', 'policy', 'knowledge', 'address', 'phone'),
    'seo': ('seo', 'navigation', 'link', 'route', 'canonical', 'title', 'heading', 'redesign'),
    'accessibility': ('accessib', 'button', 'form', 'layout', 'cta', 'design', 'label', 'contrast'),
}


def selected(proposal):
    text = json.dumps({'request': proposal.get('original_request'), 'changes': proposal.get('proposed_changes')}).lower()
    return [domain for domain, terms in DOMAINS.items() if any(term in text for term in terms)]


def plan(proposal, references):
    details = {
        'business': 'Compare supplied pricing and policy references; authority, approval and checkout require confirmation.',
        'facts': 'Check explicitly preserved source facts; source agreement does not establish real-world truth.',
        'seo': 'Inspect affected-page headings, literal title, canonical and robots metadata for source regressions.',
        'accessibility': 'Inspect literal control names, image alt attributes and local ARIA references; rendered checks remain required.',
    }
    return [{'domain': domain, 'status': 'planned', 'scope': details[domain],
             'evidence_files': sorted({ref['file'] for ref in references})} for domain in selected(proposal)]


def _issues(content, domain):
    tree = SourceTree(content)
    issues = []
    if domain == 'seo':
        h1s = [n for n in tree.nodes if n.tag == 'h1']
        if not h1s:
            issues.append(('missing_h1', 1, 'No literal h1 found in page source'))
        if len(h1s) > 1:
            issues.append(('multiple_h1', h1s[1].line, 'Multiple literal h1 elements; review heading structure'))
        for node in tree.nodes:
            if node.tag == 'base' and 'title' not in node.attrs:
                issues.append(('missing_layout_title', node.line, 'Base component lost its literal title property'))
            if node.tag == 'title' and not node.text():
                issues.append(('empty_title', node.line, 'Empty literal title'))
            if node.tag == 'meta' and node.attrs.get('name', '').lower() == 'robots' and 'noindex' in node.attrs.get('content', '').lower():
                issues.append(('noindex', node.line, 'Literal robots metadata contains noindex'))
    elif domain == 'accessibility':
        ids = {n.attrs['id'] for n in tree.nodes if n.attrs.get('id')}
        for node in tree.nodes:
            # Dynamic Astro expressions and component-rendered names need a browser.
            if '{' in node.text() or any('{' in str(v) for v in node.attrs.values()):
                continue
            if node.tag == 'img' and 'alt' not in node.attrs:
                issues.append(('image_missing_alt', node.line, 'Literal image lacks an alt attribute'))
            if node.tag in {'a', 'button'} and not (node.text() or node.attrs.get('aria-label') or node.attrs.get('aria-labelledby')):
                descendants = [n for n in tree.nodes if n.parent is node]
                if not any(n.attrs.get('alt') for n in descendants):
                    issues.append(('control_missing_name', node.line, 'Literal link/button has no visible text or explicit name; rendered name needs confirmation'))
            for ident in (node.attrs.get('aria-labelledby') or '').split():
                if ident not in ids:
                    issues.append(('local_aria_reference_missing', node.line, 'ARIA label reference not found in this page source: ' + ident))
    return issues


def verify(proposal, before, after, changed, contract_checks, scope_checks=None):
    results = []
    for domain in selected(proposal):
        if domain in {'seo', 'accessibility'}:
            evidence = []
            for path in changed:
                if not path.endswith('.astro'):
                    continue
                old = Counter(code for code, _, _ in _issues(before.get(path, ''), domain))
                for code, line, detail in _issues(after.get(path, ''), domain):
                    if old[code]:
                        old[code] -= 1
                    else:
                        evidence.append({'file': path, 'line': line, 'code': code, 'detail': detail})
                if domain == 'seo':
                    def metadata(content):
                        return [(n.tag, n.attrs.get('href'), n.attrs.get('content'), n.text())
                                for n in SourceTree(content).nodes
                                if n.tag == 'title' or (n.tag == 'link' and n.attrs.get('rel') == 'canonical')]
                    authorized_metadata = any(c['file'] == path and c.get('outcome_change') and c['evidence'].get('tag') in {'title', 'link'} for c in contract_checks) and any(c['file'] == path and c['status'] == 'passed' for c in (scope_checks or []))
                    if metadata(before.get(path, '')) != metadata(after.get(path, '')) and not authorized_metadata:
                        evidence.append({'file': path, 'line': 1, 'code': 'metadata_changed',
                                         'detail': 'Literal title or canonical metadata changed; confirm intent'})
            results.append({'domain': domain, 'check': 'source_regressions', 'status': 'review_required' if evidence else 'completed',
                            'evidence': evidence, 'checked_files': [p for p in changed if p.endswith('.astro')],
                            'detail': 'Compared literal source indicators only; this is not a rendered audit or an SEO outcome assessment.'})
            results.append({'domain': domain, 'check': 'rendered_accessibility' if domain == 'accessibility' else 'runtime_seo',
                            'status': 'not_run', 'evidence': [],
                            'detail': 'Browser contrast, keyboard and computed names not tested.' if domain == 'accessibility' else 'Indexability, live routes, shared layout output and search outcomes not tested.'})
        else:
            invariants = [c for c in contract_checks if c['kind'] in {'literal_preserved', 'element_unchanged', 'file_unchanged'}]
            results.append({'domain': domain, 'check': 'explicit_source_preservation',
                            'status': 'completed' if invariants and all(c['status'] == 'passed' for c in invariants) else 'not_assessed',
                            'evidence': [c['evidence'] for c in invariants],
                            'detail': 'Only caller-specified source invariants were checked. Business approval, policy authority, external checkout and real-world factual accuracy are not verified.'})
    return results
