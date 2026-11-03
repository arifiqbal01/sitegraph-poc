"""Regression coverage for the live Starter-card verification report."""
import copy
import unittest
from unittest.mock import patch
from api import contracts, outcomes, safeguards, ai, checkpoints as cp, workspace
import test_workflow as wf
from test_outcomes import PRICING


class ScopedSourceTests(unittest.TestCase):
    before = '<section class="plan" aria-labelledby="starter-heading"><h2 id="starter-heading">Starter</h2><p>Starter remains the plan name</p></section>'

    def check(self, entity, field, new, candidate):
        return outcomes.assess({'entity': entity, 'field': field, 'new_value': new}, self.before, candidate)

    def test_heading_does_not_require_removing_every_starter_mention(self):
        after = self.before.replace('>Starter</h2>', '>Starter – Ideal for small teams</h2>')
        self.assertEqual(self.check('h2#starter-heading', 'text', 'Starter – Ideal for small teams', after)['status'], 'passed')

    def test_insertion_checks_actual_parent_and_duplicate_identity(self):
        selector = 'section.plan[aria-labelledby="starter-heading"] > p.note'
        fragment = '<p class="note">No hidden fees</p>'
        after = self.before.replace('</section>', fragment + '</section>')
        self.assertEqual(self.check(selector, 'html', fragment, after)['status'], 'passed')
        for bad in [self.before + fragment, after.replace(fragment, fragment * 2)]:
            self.assertEqual(self.check(selector, 'html', fragment, bad)['status'], 'not_assessed')
        self.assertEqual(self.check(selector, 'html', fragment, after.replace('No hidden fees', 'Wrong promise'))['status'], 'failed')

    def test_nth_child_and_fragment_siblings(self):
        selector = 'section.plan > ul > li:nth-child(2)'
        after = '<section class="plan"><ul><li>Feature</li><li>Standard email support</li></ul></section>'
        self.assertEqual(self.check(selector, 'text', 'Standard email support', after)['status'], 'passed')
        after = '<p><span data-fact="price">$29.90</span><small>/mo</small></p>'
        self.assertEqual(self.check('span[data-fact="price"]', 'html', '<span data-fact="price">$29.90</span><small>/mo</small>', after)['status'], 'passed')

    def test_dynamic_and_unsupported_selector_are_not_clean(self):
        self.assertEqual(self.check('h2#starter-heading', 'text', 'Starter', self.before.replace('>Starter</h2>', '>{name}</h2>'))['status'], 'not_assessed')
        self.assertEqual(self.check('h2:has(script)', 'text', 'Starter', self.before)['status'], 'not_assessed')

    def test_literal_heading_tags_only(self):
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section']:
            contracts._locator({'tag': tag})
        for tag in ['h2#starter', 'h2 script', '{tag}', 'h₂', '2h', '']:
            with self.assertRaises(ValueError):
                contracts._locator({'tag': tag})

    def test_human_summary_includes_executed_evidence_only(self):
        runtime = {'builds': [{'artifact': 'candidate', 'status': 'passed'}], 'pages': [
            {'route': '/pricing', 'status': 200, 'accessibility': {'violations': [], 'incomplete': []}, 'keyboard': {'reachable': True}}]}
        result = outcomes.verified_summary(runtime, {'status': 'completed'}, [])
        self.assertIn('candidate build passed', result)
        self.assertIn('Tested CTA keyboard reachability passed', result)
        self.assertEqual(outcomes.verified_summary({}, {'status': 'not_assessed'}, []), [])


class DiagnosticsTests(unittest.TestCase):
    def review(self, response=None, error=None):
        with patch.object(ai, 'structured', return_value=response, side_effect=error):
            return safeguards.review('Improve card', {'x': 'before'}, {'x': 'No hidden fees'}, ['x'])

    def test_rate_limit_is_sanitized_and_retryable(self):
        error = ai.ModelRequestError('secret provider response', 'provider_rate_limited', 429,
                                     provider_status=429, retry_after_seconds=31)
        result = self.review(error=error)
        self.assertEqual(result['error']['code'], 'provider_rate_limited')
        self.assertEqual(result['error']['retry_after_seconds'], 31)
        self.assertNotIn('secret', str(result))
        self.assertEqual(result['status'], 'unavailable')

    def test_unknown_promise_can_be_uncertainty_without_inventing_policy(self):
        finding = {'domain': 'business', 'classification': 'insufficient_evidence', 'detail': 'Fee promise lacks supplied evidence',
                   'evidence': [{'version': 'candidate', 'file': 'x', 'line': 1, 'quote': 'No hidden fees'}]}
        result = self.review({'findings': [finding], 'limitations': []})
        self.assertEqual(result['status'], 'review_required')
        bad = copy.deepcopy(finding); bad['evidence'][0]['quote'] = 'fabricated'
        self.assertEqual(self.review({'findings': [bad], 'limitations': []})['error']['code'], 'review_invalid_evidence')

    def test_new_promise_remains_visible_without_semantic_reviewer(self):
        path = 'demo-site/src/pages/pricing.astro'
        inventory = safeguards.changed_text({path: '<p>Email support</p>'},
                                            {path: '<p>Email support</p><p>No hidden fees</p>'}, [path])
        self.assertEqual([x['text'] for x in inventory], ['No hidden fees'])
        self.assertEqual(inventory[0]['classification'], 'not_assessed')

    def test_timeout_and_invalid_json_are_distinct(self):
        self.assertEqual(self.review(error=TimeoutError())['error']['code'], 'review_timeout')
        self.assertEqual(self.review(response={})['error']['code'], 'review_invalid_response')


class IntegrationTests(unittest.TestCase):
    def fixture(self):
        helper = wf.WorkflowTests(); fixture = helper.fixture()
        self.addCleanup(helper.doCleanups)
        return helper, fixture

    def test_partial_checks_and_heading_references(self):
        helper, fixture = self.fixture()
        raw = wf.raw_proposal(fixture)
        raw['proposed_changes'] = [{'action': 'update', 'target': '/pricing', 'entity': 'h2#starter-heading',
                                    'field': 'text', 'reason': 'Clearer card', 'old_value': 'Starter', 'new_value': 'Starter – Ideal for small teams'}]
        raw['verification_contract']['checks'] = [
            {'id': 'heading', 'kind': 'text_equals', 'file': PRICING, 'locator': {'tag': 'h2', 'attributes': {'id': 'starter-heading'}}, 'expected': 'Starter – Ideal for small teams'},
            {'id': 'bad', 'kind': 'unknown', 'file': PRICING}]
        report = cp.analyze(helper.propose(fixture, raw))
        self.assertEqual(len(report['suggestion_expectations']['checks']), 1)
        result = fixture.verify(report, {PRICING: fixture.baseline[PRICING].replace('>Starter</h2>', '>Starter – Ideal for small teams</h2>')})
        self.assertEqual(result['missed_references'], [])
        self.assertEqual(result['outcome_checks'][0]['status'], 'passed')
        self.assertEqual(result['suggestion_checks'][0]['status'], 'passed')
        self.assertEqual(result['decision'], 'review_required')  # invalid sibling still disclosed
        self.assertEqual(len(result['candidate_digest']), 64)

    def test_editor_uses_saved_intent_instead_of_retry_description(self):
        helper, fixture = self.fixture()
        report = cp.analyze(helper.propose(fixture))
        with patch.object(workspace, 'ROOT', fixture.root), patch.object(workspace, 'SOURCE', fixture.root/'demo-site/src'), \
             patch.object(ai, 'plan', return_value={}) as planner, \
             patch.object(ai, 'propose_edits', return_value={'edits': [{'path': PRICING, 'content': fixture.candidate()}]}) as editor:
            workspace.draft('Create isolated draft', change_id=report['change_id'])
        for call in [planner.call_args, editor.call_args]:
            self.assertIn(report['original_request'], call.args[0])
            self.assertIn('Learn more about Starter', call.args[0])
            self.assertNotIn('Create isolated draft', call.args[0])
