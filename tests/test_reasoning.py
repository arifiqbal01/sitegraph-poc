import unittest
from unittest.mock import patch
from api import reasoning

class ReasoningTests(unittest.TestCase):
    def brief(self):
        return {'intent': 'Make Starter more competitive; price needs confirmation',
                'investigations': [{'check': 'business_consistency', 'classification': 'potentially_impacted',
                                   'reason': 'Confirm approved pricing policy',
                                   'evidence': [{'file': 'knowledge/pricing.md', 'line': 1, 'quote': 'Starter $29.90'}]}],
                'uncertainties': ['New price not supplied; do not infer one.']}

    def run_brief(self, response):
        with patch.object(reasoning.ai, 'structured', return_value=response):
            return reasoning.implementation_brief({'use_ai': True, 'original_request': 'Make Starter competitive'},
                                                  {'knowledge/pricing.md': 'Starter $29.90'})

    def test_disabled_makes_no_call(self):
        with patch.object(reasoning.ai, 'structured') as call:
            self.assertEqual(reasoning.implementation_brief({}, {})['status'], 'disabled')
            call.assert_not_called()

    def test_grounded_brief(self):
        r = self.run_brief(self.brief())
        self.assertEqual(r['status'], 'completed')
        self.assertTrue(r['advisory_only'])
        self.assertEqual(r['investigations'][0]['execution_status'], 'not_run')
        self.assertIn('New price', r['uncertainties'][0])

    def test_rejects_invented_citations(self):
        for field, value in [('file', 'invented.md'), ('line', 2), ('quote', 'Starter $19.90'), ('quote', ''), ('line', True)]:
            with self.subTest(field=field, value=value):
                data = self.brief()
                data['investigations'][0]['evidence'][0][field] = value
                self.assertEqual(self.run_brief(data)['status'], 'unavailable')

    def test_malformed_outputs(self):
        for data in ([], {}, {'intent': 'x', 'investigations': None, 'uncertainties': []}):
            with self.subTest(data=data):
                self.assertEqual(self.run_brief(data)['status'], 'unavailable')

    def test_unknown_check(self):
        data = self.brief()
        data['investigations'][0]['check'] = 'publish'
        self.assertEqual(self.run_brief(data)['status'], 'unavailable')

    def test_provider_failure_is_sanitized(self):
        with patch.object(reasoning.ai, 'structured', side_effect=RuntimeError('secret-token')):
            r = reasoning.implementation_brief({'use_ai': True}, {})
        self.assertEqual(r['status'], 'unavailable')
        self.assertNotIn('secret-token', str(r))

    def test_evidence_budget(self):
        with patch.object(reasoning, 'MAX_CHARS', 5), patch.object(reasoning.ai, 'structured', return_value=self.brief()) as call:
            r = reasoning.implementation_brief({'use_ai': True}, {'knowledge/pricing.md': 'Starter $29.90'})
        self.assertTrue(call.call_args.args[1]['evidence_truncated'])
        self.assertEqual(r['status'], 'unavailable')
