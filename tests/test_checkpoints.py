import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api import checkpoints as cp, workspace, graph

PAGE = 'demo-site/src/pages/'

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.baseline = {
            PAGE+'index.astro': '<a href="/services">services</a> Starter $29.90',
            PAGE+'pricing.astro': 'Starter $29.90',
            PAGE+'faq.astro': '<a href="/services">services</a> Starter $29.90',
            PAGE+'services.astro': '<h1>Services</h1>',
            PAGE+'services/seo.astro': '<h1>SEO</h1>',
            'knowledge/pricing.md': 'Approved Starter price $29.90',
        }
        for name, text in self.baseline.items():
            p = self.root/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        for module, name, value in [
            (cp, 'ROOT', self.root), (cp, 'PAGES', self.root/PAGE),
            (cp, 'KNOWLEDGE', self.root/'knowledge'), (cp, 'STORE', self.root/'changes'),
            (graph, 'ROOT', self.root), (graph, 'SITE', self.root/'demo-site/src'),
            (graph, 'KNOWLEDGE', self.root/'knowledge'), (graph, 'DB', self.root/'graph.sqlite'),
            (workspace, 'WORKSPACES', self.root/'workspaces'),
        ]:
            p = patch.object(module, name, value)
            p.start()
            self.addCleanup(p.stop)

    def analyze(self, pricing=False, **overrides):
        change = dict(action='update', target='/pricing' if pricing else '/',
                      entity='Starter' if pricing else 'homepage_navigation',
                      field='monthly_price' if pricing else 'internal_link',
                      old_value='$29.90' if pricing else '/services',
                      new_value='$19.90' if pricing else '/services/seo')
        change.update(overrides)
        return cp.analyze({'proposed_changes': [change]})

    def verify(self, report, edits=None):
        draft_id = 'a'*32
        folder = workspace.WORKSPACES/draft_id
        folder.mkdir(parents=True)
        (folder/'proposal.json').write_text(json.dumps({'change_id': report['change_id']}))
        preview = folder/'preview/pages'
        for name, text in self.baseline.items():
            if name.startswith(PAGE):
                p = preview/name[len(PAGE):]
                p.parent.mkdir(parents=True, exist_ok=True)
                value = (edits or {}).get(name, text)
                if value is not None:
                    p.write_text(value)
        return cp.verify(report['change_id'], draft_id)

    def test_scoped_navigation_passes(self):
        report = self.analyze()
        result = self.verify(report, {PAGE+'index.astro': self.baseline[PAGE+'index.astro'].replace('"/services"', '"/services/seo"')})
        self.assertEqual(result['decision'], 'no_detected_blockers')
        self.assertEqual(result['missed_references'], [])
        self.assertEqual(result['removed_internal_links'], [])
        self.assertIn('/faq', result['related_routes_unchanged'])
        self.assertEqual(result['destination_checks'][0]['status'], 'exists')
        self.assertEqual(cp.load(report['change_id'])['baseline'], self.baseline)
        self.assertEqual((self.root/PAGE/'index.astro').read_text(), self.baseline[PAGE+'index.astro'])

    def test_no_edit_requires_review(self):
        self.assertEqual(self.verify(self.analyze())['decision'], 'review_required')

    def test_missing_destination(self):
        r = self.verify(self.analyze(new_value='/missing'), {PAGE+'index.astro': '<a href="/missing">services</a>'})
        self.assertEqual(r['destination_checks'][0]['status'], 'missing')
        self.assertEqual(r['decision'], 'review_required')

    def test_unknown_target(self):
        self.assertEqual(self.verify(self.analyze(target='/missing'))['decision'], 'review_required')

    def test_related_navigation_edit_is_unexpected(self):
        edits = {p: text.replace('"/services"', '"/services/seo"') for p, text in self.baseline.items() if p.endswith('index.astro') or p.endswith('faq.astro')}
        r = self.verify(self.analyze(), edits)
        self.assertIn(PAGE+'faq.astro', r['unexpected_changes'])
        self.assertEqual(r['decision'], 'review_required')

    def test_unrelated_change(self):
        r = self.verify(self.analyze(), {PAGE+'services/seo.astro': 'unrelated modification'})
        self.assertIn(PAGE+'services/seo.astro', r['unexpected_changes'])

    def test_missing_preview_page_is_detected(self):
        r = self.verify(self.analyze(), {PAGE+'services/seo.astro': None})
        self.assertIn(PAGE+'services/seo.astro', r['unexpected_changes'])
        self.assertEqual(r['decision'], 'review_required')

    def test_price_pages_updated_knowledge_missed(self):
        edits = {p: text.replace('$29.90', '$19.90') for p, text in self.baseline.items() if p.endswith('.astro')}
        r = self.verify(self.analyze(pricing=True), edits)
        self.assertEqual(len(r['changed_files']), 3)
        self.assertEqual([x['file'] for x in r['missed_references']], ['knowledge/pricing.md'])
        self.assertEqual(r['decision'], 'review_required')

    def test_price_faq_and_knowledge_missed(self):
        edits = {PAGE+p: self.baseline[PAGE+p].replace('$29.90', '$19.90') for p in ('index.astro', 'pricing.astro')}
        r = self.verify(self.analyze(pricing=True), edits)
        self.assertEqual({x['file'] for x in r['missed_references']}, {PAGE+'faq.astro', 'knowledge/pricing.md'})

    def test_exact_href(self):
        self.assertEqual(cp._nav_refs('<a href="/services/seo">SEO</a>', '/services'), [])
        self.assertEqual(cp._nav_refs("<a href='/services'>Services</a>", '/services'), [1])

    def test_mismatched_analysis_rejected(self):
        r = self.analyze()
        self.verify(r)
        other = self.analyze()
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            cp.verify(other['change_id'], 'a'*32)

    def test_invalid_identifier(self):
        with self.assertRaises(ValueError):
            cp.load('../escape')

    def test_ai_brief_persisted_without_changing_references(self):
        from api import reasoning
        raw = {'intent': 'Inspect navigation', 'investigations': [
            {'check': 'navigation', 'classification': 'context_only', 'reason': 'Inspect link',
             'evidence': [{'file': PAGE+'index.astro', 'line': 1, 'quote': 'href="/services"'}]}],
            'uncertainties': []}
        with patch.object(reasoning.ai, 'structured', return_value=raw):
            report = cp.analyze({'use_ai': True, 'proposed_changes': [
                {'target': '/', 'field': 'internal_link', 'old_value': '/services', 'new_value': '/services/seo'}]})
        self.assertEqual(cp.load(report['change_id'])['report']['implementation_brief']['status'], 'completed')
        self.assertEqual(self.verify(report)['decision'], 'review_required')

    def test_ai_failure_preserves_static_analysis(self):
        from api import reasoning
        with patch.object(reasoning.ai, 'structured', side_effect=ValueError('offline')):
            report = cp.analyze({'use_ai': True, 'proposed_changes': [
                {'target': '/', 'field': 'internal_link', 'old_value': '/services', 'new_value': '/services/seo'}]})
        self.assertEqual(report['implementation_brief']['status'], 'unavailable')
        self.assertTrue(report['confirmed_references'])
        self.assertEqual(self.verify(report)['decision'], 'review_required')
