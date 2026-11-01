import json
from unittest.mock import patch
from test_checkpoints import CheckpointFixture, PAGE
from api import checkpoints as cp, workspace, contracts

PRICING = PAGE+'pricing.astro'
CONTENT = '''---
import Base from '../layouts/Base.astro';
---
<Base title="Pricing">
<h1>Pricing</h1>
<section aria-labelledby="starter-heading">
<h2 id="starter-heading">Starter</h2>
<p>Starter $29.90 monthly</p>
<ul><li>Three team members</li><li>Email support</li></ul>
<a class="button" href="/faq">Starter plan questions</a>
</section>
<section><h2>Growth</h2><p>Growth $69.90</p></section>
</Base>'''
LOCATOR = {'tag': 'a', 'attributes': {'class': 'button'},
           'within': {'tag': 'section', 'attributes': {'aria-labelledby': 'starter-heading'}}}
NEW_TEXT = 'Learn more about Starter'


def contract():
    return {'allowed_edit_files': [PRICING], 'checks': [
        {'id': 'cta-copy', 'kind': 'text_equals', 'file': PRICING, 'locator': LOCATOR, 'expected': NEW_TEXT},
        {'id': 'cta-destination', 'kind': 'attribute_equals', 'file': PRICING, 'locator': LOCATOR, 'attribute': 'href', 'expected': '/faq'},
        {'id': 'starter-price', 'kind': 'literal_preserved', 'file': PRICING, 'expected': '$29.90'},
        {'id': 'features', 'kind': 'element_unchanged', 'file': PRICING, 'locator': {'tag': 'ul'}},
        {'id': 'policy', 'kind': 'file_unchanged', 'file': 'knowledge/pricing.md'},
    ]}


class OutcomeTests(CheckpointFixture):
    def setUp(self):
        super().setUp()
        self.baseline[PRICING] = CONTENT
        (self.root/PRICING).write_text(CONTENT)

    def report(self, rules=True):
        return cp.analyze({'original_request': 'Improve Starter CTA, preserve price and facts',
                           'proposed_changes': [{'target': '/pricing', 'field': 'pricing_presentation', 'entity': 'Starter'}],
                           'implementation_contract': contract() if rules else None})

    def candidate(self, text=NEW_TEXT):
        return CONTENT.replace('Starter plan questions', text)

    def test_correct_cta_and_invariants_pass(self):
        r = self.verify(self.report(), {PRICING: self.candidate()})
        self.assertEqual(r['decision'], 'no_detected_blockers')
        self.assertTrue(all(c['status'] == 'passed' for c in r['contract_checks']))
        self.assertEqual(r['outcome_checks'][0]['status'], 'passed')
        self.assertEqual(r['scope_checks'][0]['status'], 'passed')
        self.assertIn('cta-copy', r['human_report']['verified'])
        self.assertTrue(any(x['status'] == 'not_run' for x in r['investigation_results']))

    def test_legacy_vague_request_requires_review(self):
        r = self.verify(self.report(False), {PRICING: self.candidate()})
        self.assertEqual(r['decision'], 'review_required')
        self.assertEqual(r['outcome_checks'][0]['status'], 'not_assessed')
        self.assertTrue(r['human_report']['requires_review'])

    def test_no_edit_is_not_an_outcome(self):
        self.assertEqual(self.verify(self.report())['decision'], 'review_required')

    def test_wrong_copy(self):
        r = self.verify(self.report(), {PRICING: self.candidate('Wrong CTA')})
        self.assertEqual(r['contract_checks'][0]['status'], 'failed')
        self.assertEqual(r['decision'], 'review_required')

    def test_wrong_destination(self):
        r = self.verify(self.report(), {PRICING: self.candidate().replace('href="/faq"', 'href="/services"')})
        self.assertEqual(r['contract_checks'][1]['status'], 'failed')
        self.assertEqual(r['decision'], 'review_required')

    def test_price_change(self):
        r = self.verify(self.report(), {PRICING: self.candidate().replace('$29.90', '$19.90')})
        self.assertEqual(r['contract_checks'][2]['status'], 'failed')
        self.assertEqual(r['decision'], 'review_required')

    def test_feature_change(self):
        r = self.verify(self.report(), {PRICING: self.candidate().replace('Three team members', 'Ten team members')})
        self.assertEqual(r['contract_checks'][3]['status'], 'failed')
        self.assertEqual(r['decision'], 'review_required')

    def test_unrelated_same_page_change(self):
        r = self.verify(self.report(), {PRICING: self.candidate().replace('$69.90', '$9.90')})
        self.assertTrue(all(c['status'] == 'passed' for c in r['contract_checks']))
        self.assertEqual(r['scope_checks'][0]['status'], 'needs_review')
        self.assertEqual(r['decision'], 'review_required')

    def test_candidate_ambiguous_locator(self):
        r = self.verify(self.report(), {PRICING: self.candidate().replace('</section>', '<a class="button" href="/faq">extra</a></section>', 1)})
        self.assertEqual(r['contract_checks'][0]['status'], 'not_assessed')
        self.assertEqual(r['decision'], 'review_required')

    def test_candidate_dynamic_attribute_unassessed(self):
        r = self.verify(self.report(), {PRICING: self.candidate().replace('href="/faq"', 'href={destination}')})
        self.assertEqual(r['contract_checks'][0]['status'], 'not_assessed')
        self.assertEqual(r['decision'], 'review_required')

    def test_invalid_contracts_rejected(self):
        for edit in ('missing-file', 'ambiguous', 'unsupported', 'invented-fact', 'wrong-index'):
            rules = contract()
            if edit == 'missing-file': rules['allowed_edit_files'] = ['../escape']
            if edit == 'ambiguous': rules['checks'][0]['locator'] = {'tag': 'h2'}
            if edit == 'unsupported': rules['checks'][0]['kind'] = 'publish'
            if edit == 'invented-fact': rules['checks'][2]['expected'] = 'nonexistent fact'
            if edit == 'wrong-index': rules['checks'][0]['change_index'] = 3
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                cp.validate_contract(rules, self.baseline, [{'target': '/pricing'}])

    def test_one_outcome_cannot_cover_two_proposals(self):
        r = cp.analyze({'proposed_changes': [{'target': '/pricing', 'field': 'cta'}, {'target': '/pricing', 'field': 'features'}],
                        'implementation_contract': contract()})
        result = self.verify(r, {PRICING: self.candidate()})
        self.assertEqual(result['outcome_checks'][1]['status'], 'not_assessed')
        self.assertEqual(result['decision'], 'review_required')

    def test_contract_bound_through_draft_apply_and_verify(self):
        report = self.report(False)
        with patch.object(workspace, 'ROOT', self.root), patch.object(workspace, 'SOURCE', self.root/'demo-site/src'), \
             patch.object(workspace.ai, 'plan', return_value={'entity': 'Starter'}), \
             patch.object(workspace.ai, 'propose_edits', return_value={'edits': [{'path': PRICING, 'content': self.candidate()}]}) as editor:
            draft = workspace.draft('Improve CTA; preserve price', report['change_id'], contract())
            self.assertEqual(editor.call_args.args[2]['implementation_contract'], contract())
            self.assertEqual(draft['implementation_contract'], contract())
            workspace.apply(draft['draft_id'])
        result = cp.verify(report['change_id'], draft['draft_id'])
        self.assertEqual(result['decision'], 'no_detected_blockers')
        self.assertEqual(cp.load(report['change_id'])['baseline'][PRICING], CONTENT)
        self.assertEqual((self.root/PRICING).read_text(), CONTENT)

    def test_analysis_contract_cannot_be_relaxed(self):
        r = self.report()
        self.verify(r, {PRICING: self.candidate()})
        path = workspace.WORKSPACES/('a'*32)/'proposal.json'
        data = json.loads(path.read_text())
        rules = contract()
        rules['checks'].pop()
        data['implementation_contract'] = rules
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'immutable'):
            cp.verify(r['change_id'], 'a'*32)

    def test_draft_rejects_baseline_drift_before_model_call(self):
        report = self.report(False)
        (self.root/PRICING).write_text(CONTENT.replace('$29.90', '$39.90'))
        with patch.object(workspace, 'ROOT', self.root), patch.object(workspace, 'SOURCE', self.root/'demo-site/src'), \
             patch.object(workspace.ai, 'plan') as planner:
            with self.assertRaisesRegex(ValueError, 'Source changed since analysis'):
                workspace.draft('Improve CTA', report['change_id'], contract())
            planner.assert_not_called()

    def test_draft_cannot_relax_saved_contract(self):
        report = self.report()
        rules = contract()
        rules['checks'].pop()
        with patch.object(workspace, 'ROOT', self.root), patch.object(workspace, 'SOURCE', self.root/'demo-site/src'), \
             patch.object(workspace.ai, 'plan') as planner:
            with self.assertRaisesRegex(ValueError, 'Cannot override'):
                workspace.draft('Improve CTA', report['change_id'], rules)
            planner.assert_not_called()

    def test_new_unexpected_page_detected(self):
        report = self.report()
        self.verify(report, {PRICING: self.candidate()})
        new = workspace.WORKSPACES/('a'*32)/'preview/pages/unexpected.astro'
        new.write_text('<h1>Unexpected</h1>')
        r = cp.verify(report['change_id'], 'a'*32)
        self.assertIn(PAGE+'unexpected.astro', r['unexpected_changes'])
        self.assertEqual(r['decision'], 'review_required')

    def test_explicit_contrast_request_not_proven_by_source_change(self):
        report = cp.analyze({'proposed_changes': [{'target': '/pricing', 'field': 'contrast', 'old_value': 'Questions', 'new_value': 'Learn more'}]})
        r = self.verify(report, {PRICING: CONTENT.replace('Questions', 'Learn more')})
        self.assertEqual(r['decision'], 'review_required')
        self.assertEqual(r['outcome_checks'][0]['status'], 'not_assessed')
        self.assertIn('runtime', r['outcome_checks'][0]['detail'])

    def test_explicit_contract_href_replacement_is_authorized(self):
        rules = contract()
        rules['checks'][1]['expected'] = '/services/seo'
        report = cp.analyze({'proposed_changes': [{'target': '/pricing', 'field': 'cta'}], 'implementation_contract': rules})
        r = self.verify(report, {PRICING: self.candidate().replace('href="/faq"', 'href="/services/seo"')})
        self.assertEqual(r['removed_internal_links'], [])
        self.assertEqual(r['destination_checks'][0]['status'], 'exists')
        self.assertEqual(r['decision'], 'no_detected_blockers')

    def test_contract_href_missing_destination(self):
        rules = contract()
        rules['checks'][1]['expected'] = '/missing'
        report = cp.analyze({'proposed_changes': [{'target': '/pricing', 'field': 'cta'}], 'implementation_contract': rules})
        r = self.verify(report, {PRICING: self.candidate().replace('href="/faq"', 'href="/missing"')})
        self.assertEqual(r['destination_checks'][0]['status'], 'missing')
        self.assertEqual(r['decision'], 'review_required')

    def test_authorized_literal_seo_title_change_passes(self):
        original = CONTENT+'<title>Old title</title>'
        self.baseline[PRICING] = original
        (self.root/PRICING).write_text(original)
        rules = {'allowed_edit_files': [PRICING], 'checks': [
            {'id': 'seo-title', 'kind': 'text_equals', 'file': PRICING, 'locator': {'tag': 'title'}, 'expected': 'New title'}]}
        report = cp.analyze({'proposed_changes': [{'target': '/pricing', 'field': 'seo_title'}], 'implementation_contract': rules})
        r = self.verify(report, {PRICING: original.replace('Old title', 'New title')})
        self.assertEqual(r['decision'], 'no_detected_blockers')
        self.assertEqual(r['investigation_results'][0]['evidence'], [])
