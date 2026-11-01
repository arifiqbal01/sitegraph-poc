import unittest
from api import investigations as impact

P = 'demo-site/src/pages/pricing.astro'
BASE = '<Base title="Pricing"><h1>Pricing</h1><a href="/faq">Questions</a></Base>'

class InvestigationTests(unittest.TestCase):
    def inspect(self, domain, candidate, original=BASE):
        proposal = {'original_request': domain, 'proposed_changes': []}
        return impact.verify(proposal, {P: original}, {P: candidate}, [P], [])

    def test_seo_removed_heading(self):
        r = self.inspect('seo', BASE.replace('<h1>Pricing</h1>', ''))
        self.assertEqual(r[0]['status'], 'review_required')
        self.assertEqual(r[0]['evidence'][0]['code'], 'missing_h1')
        self.assertEqual(r[1]['status'], 'not_run')

    def test_seo_noindex(self):
        r = self.inspect('seo', BASE+'<meta name="robots" content="noindex,nofollow">')
        self.assertIn('noindex', [e['code'] for e in r[0]['evidence']])

    def test_seo_layout_title_removed(self):
        r = self.inspect('seo', BASE.replace(' title="Pricing"', ''))
        self.assertIn('missing_layout_title', [e['code'] for e in r[0]['evidence']])

    def test_seo_canonical_change(self):
        canonical = '<link rel="canonical" href="https://example.test/pricing">'
        r = self.inspect('seo', BASE+canonical.replace('/pricing', '/wrong'), BASE+canonical)
        self.assertIn('metadata_changed', [e['code'] for e in r[0]['evidence']])

    def test_accessibility_empty_cta(self):
        r = self.inspect('CTA accessibility', BASE.replace('>Questions</a>', '></a>'))
        self.assertEqual(r[0]['status'], 'review_required')
        self.assertIn('control_missing_name', [e['code'] for e in r[0]['evidence']])
        self.assertEqual(r[1]['check'], 'rendered_accessibility')
        self.assertEqual(r[1]['status'], 'not_run')

    def test_accessibility_missing_alt(self):
        r = self.inspect('accessibility', BASE+'<img src="example.png">')
        self.assertIn('image_missing_alt', [e['code'] for e in r[0]['evidence']])

    def test_local_aria_reference(self):
        r = self.inspect('accessibility', BASE+'<section aria-labelledby="missing">Content</section>')
        self.assertIn('local_aria_reference_missing', [e['code'] for e in r[0]['evidence']])

    def test_preexisting_source_issue_not_new_regression(self):
        old = BASE+'<img src="old.png">'
        self.assertEqual(self.inspect('accessibility', old.replace('Questions', 'Learn more'), old)[0]['evidence'], [])

    def test_valid_cta_no_invented_failure(self):
        self.assertEqual(self.inspect('accessibility', BASE.replace('Questions', 'Learn more'))[0]['status'], 'completed')

    def test_facts_and_business_not_claimed_verified(self):
        for term in ('facts', 'pricing'):
            with self.subTest(term=term):
                r = self.inspect(term, BASE)
                self.assertEqual(r[0]['status'], 'not_assessed')
                self.assertIn('real-world', r[0]['detail'])

    def test_selective_investigation(self):
        self.assertEqual(impact.selected({'original_request': 'Change monthly pricing', 'proposed_changes': []}), ['business'])
        self.assertEqual(impact.selected({'original_request': 'Update facts and CTA', 'proposed_changes': []}), ['facts', 'accessibility'])
