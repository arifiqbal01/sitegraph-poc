"""Bounded literal source outcome checks. Unsupported selectors remain uncertainty."""
import re
from .source import SourceTree, Node
from .contracts import dynamic


def select(tree, selector):
    # Deliberately bounded CSS subset: literal tag/id/classes/quoted attributes,
    # direct children and nth-child. No executable selectors or inferred identity.
    parts = re.split(r'\s*>\s*', selector.strip())
    if not 1 <= len(parts) <= 5:
        raise ValueError('Unsupported selector')
    def matches(node, part):
        tag = re.match(r'[A-Za-z][A-Za-z0-9]*', part)
        if not tag:
            raise ValueError('Unsupported selector')
        rest = part[tag.end():]
        good = node.tag == tag.group().lower()
        while rest:
            token = re.match(r'''(?:#([\w-]+)|\.([\w-]+)|\[([\w-]+)=["']([^"']*)["']\]|:nth-child\(([1-9][0-9]*)\))''', rest)
            if not token:
                raise ValueError('Unsupported selector')
            ident, cls, attr, value, nth = token.groups()
            if ident:
                good &= node.attrs.get('id') == ident
            elif cls:
                good &= cls in node.attrs.get('class', '').split()
            elif attr:
                good &= node.attrs.get(attr) == value
            else:
                siblings = [c for c in node.parent.children if isinstance(c, Node)]
                good &= next(i for i, c in enumerate(siblings, 1) if c is node) == int(nth)
            rest = rest[token.end():]
        return good
    selected = []
    for node in tree.nodes:
        current = node
        good = True
        for part in reversed(parts):
            if current is None or not matches(current, part):
                good = False
                break
            current = current.parent
        if good:
            selected.append(node)
    return selected


def signature(node):
    return node.tag, sorted(node.attrs.items()), tuple(signature(c) if isinstance(c, Node) else ' '.join(c.split()) for c in node.children if isinstance(c, Node) or c.strip())


def assess(change, before, after):
    field = str(change.get('field', '')).lower()
    if field not in {'text', 'html'} or not isinstance(change.get('new_value'), str):
        return None
    selector = change.get('entity', '')
    if not isinstance(selector, str):
        return None
    try:
        old = select(SourceTree(before), selector)
        new = select(SourceTree(after), selector)
    except ValueError:
        return {'status': 'not_assessed', 'detail': 'Unsupported literal entity selector; no scoped outcome inferred'}
    evidence = {'selector': selector, 'baseline_matches': len(old), 'candidate_matches': len(new)}
    if len(new) != 1 or len(old) > 1:
        return {'status': 'not_assessed', 'detail': 'Target missing or ambiguous; scoped identity cannot be established', 'evidence': evidence}
    if dynamic(new[0]):
        return {'status': 'not_assessed', 'detail': 'Dynamic target requires rendered outcome evidence', 'evidence': evidence}
    expected = change['new_value']
    if field == 'text':
        passed = new[0].text() == ' '.join(expected.split())
    else:
        fragment = SourceTree(expected)
        roots = [n for n in fragment.root.children if isinstance(n, Node)]
        if not roots or any(isinstance(c, str) and c.strip() for c in fragment.root.children):
            return {'status': 'not_assessed', 'detail': 'HTML outcome requires one element matching the scoped target', 'evidence': evidence}
        siblings = [c for c in new[0].parent.children if isinstance(c, Node)]
        start = next(i for i, c in enumerate(siblings) if c is new[0])
        observed = siblings[start:start + len(roots)]
        passed = [signature(n) for n in observed] == [signature(n) for n in roots]
        if any(dynamic(n) for n in observed):
            return {'status': 'not_assessed', 'detail': 'Dynamic fragment requires rendered evidence', 'evidence': evidence}
    evidence.update(candidate_line=new[0].line, observed=new[0].text(), expected=expected)
    return {'status': 'passed' if passed else 'failed', 'detail': 'Scoped source outcome matched' if passed else 'Scoped source outcome differs from the suggestion', 'evidence': evidence}


def verified_summary(runtime, policy, outcomes):
    verified = [f"Suggestion {x['change_index']}: explicit source outcome observed" for x in outcomes if x['status'] == 'passed']
    for build in runtime.get('builds', []):
        if build['status'] == 'passed':
            verified.append(build['artifact'] + ' build passed')
    pages = runtime.get('pages', [])
    if pages:
        verified.append(f"Browser observations: {len(pages)} across {len({p['route'] for p in pages})} routes")
        if all(p['status'] == 200 for p in pages):
            verified.append('All observed pages returned HTTP 200')
        if all(not p['accessibility']['violations'] and not p['accessibility']['incomplete'] for p in pages):
            verified.append('Selected axe checks: no violations or incomplete results in observed pages')
        keyboard = [p for p in pages if p.get('keyboard')]
        if keyboard and all(p['keyboard'].get('reachable') for p in keyboard):
            verified.append('Tested CTA keyboard reachability passed')
    if runtime.get('domain_results', {}).get('seo', {}).get('status') == 'completed' and not any(e.get('domain') == 'seo' for e in runtime.get('evidence', [])):
        verified.append('Supported rendered SEO checks completed without detected findings; indexing and ranking not assessed')
    if policy['status'] == 'completed':
        verified.append('Marked literal facts: no conflicts with frozen supplied authority detected')
    return verified
