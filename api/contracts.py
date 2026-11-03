"""Explicit caller-supplied acceptance checks; model prose is never authorization."""
import re
from .source import SourceTree

KINDS = {'text_equals', 'attribute_equals', 'element_unchanged', 'literal_preserved', 'file_unchanged'}
OUTCOMES = {'text_equals', 'attribute_equals'}


def _locator(value, nested=False):
    if not isinstance(value, dict) or not isinstance(value.get('tag'), str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', value['tag']):
        raise ValueError('Contract locator requires a literal HTML tag')
    if set(value) - {'tag', 'attributes', 'within'}:
        raise ValueError('Unknown locator fields')
    attrs = value.get('attributes', {})
    if not isinstance(attrs, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v or '{' in v for k, v in attrs.items()):
        raise ValueError('Locator attributes must be nonempty literal strings')
    if 'within' in value:
        if nested:
            raise ValueError('Only one ancestor locator is supported')
        _locator(value['within'], nested=True)


def validate(contract, baseline):
    if contract is None:
        return None
    if not isinstance(contract, dict) or set(contract) != {'allowed_edit_files', 'checks'}:
        raise ValueError('Contract requires allowed_edit_files and checks only')
    allowed = contract['allowed_edit_files']
    checks = contract['checks']
    if not isinstance(allowed, list) or not allowed or len(allowed) > 12 or any(not isinstance(p, str) or p not in baseline or not p.startswith('demo-site/src/pages/') for p in allowed):
        raise ValueError('Allowed edit files must be existing baseline pages')
    if len(set(allowed)) != len(allowed) or not isinstance(checks, list) or not checks or len(checks) > 30:
        raise ValueError('Invalid contract size or duplicate files')
    ids = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) - {'id', 'kind', 'file', 'locator', 'expected', 'attribute', 'change_index'}:
            raise ValueError('Invalid contract check')
        ident = check.get('id')
        kind = check.get('kind')
        path = check.get('file')
        if not isinstance(ident, str) or not ident.strip() or ident in ids or not isinstance(kind, str) or kind not in KINDS or not isinstance(path, str) or path not in baseline:
            raise ValueError('Check requires unique id, supported kind, and existing file')
        ids.add(ident)
        if type(check.get('change_index', 0)) is not int or check.get('change_index', 0) < 0:
            raise ValueError('change_index must be a nonnegative integer')
        if kind in OUTCOMES and path not in allowed:
            raise ValueError('Outcome checks must target an allowed edit file')
        if kind in OUTCOMES | {'literal_preserved'} and (not isinstance(check.get('expected'), str) or not check['expected'].strip()):
            raise ValueError('Check requires nonempty expected text')
        if kind == 'attribute_equals' and (not isinstance(check.get('attribute'), str) or not check['attribute'].strip()):
            raise ValueError('Attribute check requires an attribute name')
        if kind in OUTCOMES | {'element_unchanged'}:
            _locator(check.get('locator'))
            selected = SourceTree(baseline[path]).select(check['locator'])
            if len(selected) != 1:
                raise ValueError('Locator must identify exactly one baseline element: ' + ident)
            node = selected[0]
            if dynamic(node):
                raise ValueError('Dynamic Astro content requires rendered verification')
            if kind == 'attribute_equals' and check['attribute'] not in node.attrs:
                raise ValueError('Attribute must exist in baseline')
        if kind == 'literal_preserved' and check['expected'] not in baseline[path]:
            raise ValueError('Preserved literal must exist in baseline')
    # Defensive copy: persisted rules cannot share mutable caller objects.
    import json
    return json.loads(json.dumps(contract))


def evaluate(contract, before, after):
    if contract is None:
        return []
    checks = []
    for rule in contract['checks']:
        path, kind = rule['file'], rule['kind']
        original, candidate = before[path], after.get(path, '')
        evidence = {'file': path}
        before_value = after_value = None
        if kind == 'file_unchanged':
            passed = original == candidate
        elif kind == 'literal_preserved':
            expected = rule['expected']
            passed = original.count(expected) == candidate.count(expected)
            evidence.update(expected=expected, before_count=original.count(expected), after_count=candidate.count(expected))
        else:
            old = SourceTree(original).select(rule['locator'])
            new = SourceTree(candidate).select(rule['locator'])
            if len(old) != 1 or len(new) != 1:
                checks.append({'id': rule['id'], 'file': path, 'kind': kind, 'status': 'not_assessed',
                               'detail': 'Locator is missing or ambiguous in candidate; static identity cannot be established',
                               'evidence': {'file': path, 'baseline_matches': len(old), 'candidate_matches': len(new)}})
                continue
            if dynamic(new[0]):
                checks.append({'id': rule['id'], 'file': path, 'kind': kind, 'status': 'not_assessed',
                               'detail': 'Dynamic Astro expression requires rendered verification', 'evidence': evidence})
                continue
            evidence.update(baseline_line=old[0].line, candidate_line=new[0].line, tag=new[0].tag)
            if kind == 'text_equals':
                before_value, after_value = old[0].text(), new[0].text()
                passed = after_value == rule['expected']
            elif kind == 'attribute_equals':
                before_value = old[0].attrs.get(rule['attribute'])
                after_value = new[0].attrs.get(rule['attribute'])
                passed = after_value == rule['expected']
            else:
                passed = old[0].signature() == new[0].signature()
        if kind in OUTCOMES:
            evidence.update(before=before_value, after=after_value, expected=rule['expected'])
        checks.append({'id': rule['id'], 'file': path, 'kind': kind, 'status': 'passed' if passed else 'failed',
                       'attribute': rule.get('attribute'),
                       'change_index': rule.get('change_index', 0),
                       'outcome_change': kind in OUTCOMES and passed and before_value != after_value,
                       'detail': 'Explicit source assertion satisfied' if passed else 'Explicit source assertion failed',
                       'evidence': evidence})
    return checks


def dynamic(node):
    return '{' in str(node.signature()) or '}' in str(node.signature())


def scope_checks(contract, before, after):
    """Compare parsed source structure with only declared text/attribute values masked."""
    if contract is None:
        return []
    results = []
    for path in contract['allowed_edit_files']:
        signatures = []
        ambiguous = False
        for content in (before[path], after.get(path, '')):
            tree = SourceTree(content)
            text_nodes = set()
            attr_nodes = {}
            for rule in contract['checks']:
                if rule['file'] != path or rule['kind'] not in OUTCOMES:
                    continue
                nodes = tree.select(rule['locator'])
                if len(nodes) != 1 or dynamic(nodes[0]):
                    ambiguous = True
                    continue
                if rule['kind'] == 'text_equals':
                    text_nodes.add(id(nodes[0]))
                else:
                    attr_nodes.setdefault(id(nodes[0]), set()).add(rule['attribute'])
            def signature(node, mask_text=False):
                from .source import Node
                mask_text = mask_text or id(node) in text_nodes
                attrs = sorted((k, '<authorized-value>' if k in attr_nodes.get(id(node), set()) else v) for k, v in node.attrs.items())
                children = [signature(c, mask_text) if isinstance(c, Node) else ('<authorized-text>' if mask_text else ' '.join(c.split())) for c in node.children]
                # HTMLParser emits file-final newlines as root text nodes. Their
                # presence is source formatting, not an out-of-contract edit.
                # Keep interior text nodes and all element structure unchanged.
                if node is tree.root:
                    while children and children[-1] == '':
                        children.pop()
                return node.tag, attrs, children
            signatures.append(signature(tree.root))
        status = 'not_assessed' if ambiguous else ('passed' if signatures[0] == signatures[1] else 'needs_review')
        results.append({'file': path, 'status': status,
                        'detail': 'Parsed structure outside declared text/attribute changes preserved' if status == 'passed' else 'Source changes exceed declared text/attribute scope or element identity is unresolved',
                        'limitation': 'Literal source structure only; comments, rendered DOM and component internals are not compared.'})
    return results
