"""Unpredictable proposals are inputs; independent safeguards remain authoritative."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from api import ai, suggestions, safeguards, workflow, checkpoints as cp, workspace
import test_outcomes as outcomes
from test_outcomes import PRICING


def raw_proposal(fixture, price=False, question=False):
    text = 'Starter plan questions'
    raw = {
        'proposed_changes': [{'action':'update','target':'/pricing','entity':'Starter','field':'monthly_price' if price else 'cta',
                             'old_value':'$29.90' if price else text,'new_value':'$19.90' if price else 'Learn more about Starter',
                             'reason':'AI proposal from broad human intent'}],
        'source_evidence':[{'file':PRICING,'line':6,'quote':'<h1>Pricing</h1>'}],
        'preservation_suggestions':['Preserve Growth and destination'],
        'assumptions':['An inferred price is a proposal, not approved policy'] if price else ['Clearer wording may help'],
        'clarification_questions':['Is this price consistent with the billing policy?'] if question else [],
        'verification_contract':None if price else outcomes.contract(),
    }
    # The fixture line number follows its exact supplied source, not a guessed line.
    raw['source_evidence'][0]['line'] = next(i for i,line in enumerate(fixture.baseline[PRICING].splitlines(),1) if '<h1>' in line)
    return raw


class WorkflowTests(unittest.TestCase):
    def fixture(self):
        fixture=outcomes.OutcomeTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        return fixture

    def propose(self, fixture, raw=None):
        with patch.object(ai,'structured',return_value=raw or raw_proposal(fixture)):
            return suggestions.propose('Improve the Starter card')

    def test_harmful_price_proposal_is_not_filtered_or_human_approved(self):
        fixture=self.fixture()
        proposal=self.propose(fixture,raw_proposal(fixture,price=True,question=True))
        self.assertEqual(proposal['proposed_changes'][0]['new_value'],'$19.90')
        self.assertIsNone(proposal['implementation_contract'])
        self.assertEqual(proposal['suggestion_context']['origin'],'ai_generated')
        report=cp.analyze(proposal)
        self.assertTrue(report['suggestion_context']['clarification_questions'])
        self.assertIn('not_human_approved',report['expectation_provenance']['suggestion_expectations'])

    def test_fabricated_source_quote_is_rejected(self):
        fixture=self.fixture();raw=raw_proposal(fixture)
        raw['source_evidence'][0]['quote']='invented evidence'
        with self.assertRaisesRegex(ValueError,'supplied source'):
            self.propose(fixture,raw)

    def test_changed_sources_between_suggestion_and_analysis_rejected(self):
        fixture=self.fixture();proposal=self.propose(fixture)
        (fixture.root/PRICING).write_text('changed concurrently')
        with self.assertRaisesRegex(ValueError,'Sources changed'):
            cp.analyze(proposal)

    def test_invalid_model_check_does_not_prevent_draft_but_is_disclosed(self):
        fixture=self.fixture();raw=raw_proposal(fixture)
        raw['verification_contract']['checks'][0]['kind']='make_site_safe'
        report=cp.analyze(self.propose(fixture,raw))
        self.assertIsNone(report['suggestion_expectations'])
        self.assertTrue(report['suggestion_expectation_errors'])
        result=fixture.verify(report,{PRICING:fixture.candidate()})
        self.assertEqual(result['decision'],'review_required')

    def test_no_acceptance_gate_and_final_human_review_after_verify(self):
        fixture=self.fixture();proposal=self.propose(fixture)
        reviewed=[]
        def independent(*args):
            reviewed.append(args)
            return {'status':'completed','advisory_only':True,'findings':[],'evidence_truncated':False,'limitations':[]}
        with patch.object(suggestions,'propose',return_value=proposal), \
             patch.object(workspace,'ROOT',fixture.root),patch.object(workspace,'SOURCE',fixture.root/'demo-site/src'), \
             patch.object(ai,'plan',return_value={'entity':'Starter'}), \
             patch.object(ai,'propose_edits',return_value={'edits':[{'path':PRICING,'content':fixture.candidate()}]}) as editor, \
             patch.object(cp.rendered,'verify',return_value={'status':'completed','evidence':[]}), \
             patch.object(safeguards,'review',side_effect=independent):
            result=workflow.run('Improve Starter')
        self.assertEqual(result['status'],'ready_for_human_review')
        self.assertEqual(result['decision'],'no_detected_blockers')
        self.assertEqual(result['human_review'],'not_yet_reviewed')
        self.assertFalse(result['published'])
        self.assertTrue(result['preview'])
        self.assertIsNone(result['draft']['implementation_contract'])
        self.assertEqual(editor.call_args.args[2]['suggestion_context']['assumptions'],['Clearer wording may help'])
        self.assertEqual(editor.call_args.args[2]['impact_advisory']['origin'],'independent_pre_implementation_analysis_not_approval')
        self.assertEqual(result,workflow.load(result['workflow_id']))
        self.assertEqual((fixture.root/PRICING).read_text(),fixture.baseline[PRICING])
        self.assertTrue(reviewed)
        self.assertTrue(result['verification']['suggestion_checks'])
        self.assertEqual(result['verification']['contract_checks'],[])

    def test_unanswered_questions_travel_to_editor_then_human_review(self):
        fixture=self.fixture();proposal=self.propose(fixture,raw_proposal(fixture,question=True))
        with patch.object(suggestions,'propose',return_value=proposal), \
             patch.object(workspace,'ROOT',fixture.root),patch.object(workspace,'SOURCE',fixture.root/'demo-site/src'), \
             patch.object(ai,'plan',return_value={}), \
             patch.object(ai,'propose_edits',return_value={'edits':[{'path':PRICING,'content':fixture.candidate()}]}) as editor:
            result=workflow.run('Improve Starter',run_rendered=False,run_ai_review=False)
        self.assertEqual(result['status'],'ready_for_human_review')
        self.assertTrue(editor.call_args.args[2]['suggestion_context']['clarification_questions'])
        self.assertEqual(result['decision'],'review_required')
        self.assertTrue(any('Unanswered question' in x for x in result['verification']['human_report']['requires_review']))

    def test_failed_editor_retains_analysis_and_safe_error(self):
        fixture=self.fixture();proposal=self.propose(fixture)
        with patch.object(suggestions,'propose',return_value=proposal), \
             patch.object(workspace,'draft',side_effect=ai.ModelRequestError('Rate limited','provider_rate_limited',429)):
            with self.assertRaises(workflow.WorkflowFailure) as error:
                workflow.run('Improve Starter')
        result=error.exception.record
        self.assertEqual(error.exception.status_code,429)
        self.assertEqual(result['stage'],'draft')
        self.assertTrue(result['change_id'])
        self.assertEqual(workflow.load(result['workflow_id'])['status'],'failed')
        self.assertNotIn('draft_id',result)

    def test_independent_policy_checks_ignore_benign_proposal_labels(self):
        fixture=self.fixture()
        policy={'authority':'Supplied product policy','facts':{'starter-price':'$29.90'},
                'required_routes':{'starter-price':['/pricing']}}
        path='knowledge/product-facts.json'
        fixture.baseline[path]=json.dumps(policy)
        (fixture.root/path).write_text(json.dumps(policy))
        source=fixture.baseline[PRICING].replace('Starter $29.90 monthly','Starter <span data-fact="starter-price">$29.90</span> monthly')
        fixture.baseline[PRICING]=source;(fixture.root/PRICING).write_text(source)
        report=cp.analyze({'proposed_changes':[{'target':'/pricing','field':'copy','old_value':'questions','new_value':'details'}]})
        result=fixture.verify(report,{PRICING:source.replace('questions','details').replace('$29.90','$19.90')})
        self.assertEqual(result['decision'],'review_required')
        self.assertEqual(result['independent_safeguards']['policy_consistency']['evidence'][0]['expected'],'$29.90')

    def test_perfect_ai_price_fidelity_does_not_override_policy(self):
        fixture=self.fixture()
        policy_path='knowledge/product-facts.json'
        policy={'authority':'Fixture policy','facts':{'starter-price':'$29.90'},'required_routes':{'starter-price':['/pricing']}}
        fixture.baseline[policy_path]=json.dumps(policy);(fixture.root/policy_path).write_text(json.dumps(policy))
        source=fixture.baseline[PRICING].replace('Starter $29.90 monthly','Starter <span data-fact="starter-price">$29.90</span> monthly')
        fixture.baseline[PRICING]=source;(fixture.root/PRICING).write_text(source)
        raw=raw_proposal(fixture,price=True)
        raw['verification_contract']={'allowed_edit_files':[PRICING],'checks':[{
            'id':'ai-price','kind':'text_equals','file':PRICING,'locator':{'tag':'span','attributes':{'data-fact':'starter-price'}},'expected':'$19.90'}]}
        report=cp.analyze(self.propose(fixture,raw))
        result=fixture.verify(report,{PRICING:source.replace('$29.90','$19.90')})
        self.assertTrue(all(c['status']=='passed' for c in result['suggestion_checks']))
        self.assertTrue(all(c['status']=='passed' for c in result['suggestion_scope_checks']))
        self.assertEqual(result['outcome_checks'][0]['status'],'passed')
        self.assertEqual(result['decision'],'review_required')

    def test_quality_check_runs_for_unpredictable_change_field(self):
        fixture=self.fixture()
        report=cp.analyze({'proposed_changes':[{'target':'/pricing','field':'something_unexpected',
            'old_value':'Starter plan questions','new_value':'Learn more about Starter'}]})
        result=fixture.verify(report,{PRICING:fixture.candidate().replace('<h1>Pricing</h1>','')})
        self.assertEqual(result['decision'],'review_required')
        self.assertTrue(any(e['code']=='missing_h1' for r in result['investigation_results'] for e in r.get('evidence',[])))

    def test_workflow_http_returns_final_review_without_approval_request(self):
        fixture=self.fixture();proposal=self.propose(fixture)
        from api.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as client, patch.object(suggestions,'propose',return_value=proposal), \
             patch.object(workspace,'ROOT',fixture.root),patch.object(workspace,'SOURCE',fixture.root/'demo-site/src'), \
             patch.object(ai,'plan',return_value={}), \
             patch.object(ai,'propose_edits',return_value={'edits':[{'path':PRICING,'content':fixture.candidate()}]}):
            result=client.post('/workflow/run',json={'prompt':'Improve Starter','run_rendered':False,'run_ai_review':False})
            self.assertEqual(result.status_code,200,result.text)
            body=result.json();self.assertEqual(body['stage'],'human_review')
            self.assertEqual(client.get('/workflow/'+body['workflow_id']).status_code,200)


class IndependentReviewerTests(unittest.TestCase):
    def test_feature_promise_conflict_is_reviewed_without_agent_expectations(self):
        before={'knowledge/policy.md':'Starter includes email support only.','demo-site/src/pages/pricing.astro':'<p>Email support</p>'}
        after=dict(before,**{'demo-site/src/pages/pricing.astro':'<p>24/7 phone support guaranteed</p>'})
        output={'findings':[{'domain':'business','detail':'Candidate promises phone support beyond supplied policy.',
                 'evidence':[{'version':'baseline','file':'knowledge/policy.md','line':1,'quote':'email support only'},
                             {'version':'candidate','file':'demo-site/src/pages/pricing.astro','line':1,'quote':'24/7 phone support guaranteed'}]}], 'limitations':[]}
        with patch.object(ai,'structured',return_value=output) as reviewer:
            result=safeguards.review('Improve pricing',before,after,['demo-site/src/pages/pricing.astro'])
        self.assertEqual(result['status'],'review_required')
        self.assertNotIn('suggestion_context',reviewer.call_args.args[1])
        self.assertNotIn('verification_contract',reviewer.call_args.args[1])
        self.assertTrue(result['advisory_only'])

    def test_invented_review_evidence_cannot_claim_clean_verification(self):
        bad={'findings':[{'domain':'facts','detail':'invented','evidence':[{'version':'candidate','file':'x','line':1,'quote':'not there'}]}],'limitations':[]}
        with patch.object(ai,'structured',return_value=bad):
            result=safeguards.review('test',{'x':'before'},{'x':'after'},['x'])
        self.assertEqual(result['status'],'unavailable')

    def test_missing_marker_cannot_evade_policy_consistency(self):
        before={'knowledge/product-facts.json':json.dumps({'facts':{'price':'29'},'required_routes':{'price':['/pricing']}})}
        result=safeguards.policy_checks(before,{'demo-site/src/pages/pricing.astro':'<p>19</p>'})
        self.assertEqual(result['status'],'review_required')
        self.assertEqual(result['evidence'][0]['code'],'required_fact_missing')


class PreImplementationTests(unittest.TestCase):
    def test_proposed_policy_conflict_is_reported_without_blocking_implementation(self):
        before={'knowledge/product-facts.json':json.dumps({'authority':'Product policy','facts':{'starter-price':'$29.90'}})}
        result=safeguards.analyze([{'target':'/pricing','old_value':'$29.90','new_value':'$19.90'}],before)
        self.assertEqual(result['status'],'potential_conflict')
        self.assertEqual(result['evidence'][0]['proposed_value'],'$19.90')
        self.assertIn('continue isolated implementation',result['detail'])

    def test_unknown_claim_does_not_become_a_proven_conflict(self):
        before={'knowledge/product-facts.json':json.dumps({'facts':{'starter-price':'$29.90'}})}
        result=safeguards.analyze([{'target':'/pricing','field':'promise','new_value':'24/7 support'}],before)
        self.assertEqual(result['evidence'],[])

    def test_business_finding_without_policy_citation_is_unavailable(self):
        raw={'findings':[{'domain':'business','detail':'Unsupported claim','evidence':[
            {'version':'candidate','file':'x','line':1,'quote':'claim'}]}], 'limitations':[]}
        with patch.object(ai,'structured',return_value=raw):
            result=safeguards.review('test',{'x':'baseline'},{'x':'claim'},['x'])
        self.assertEqual(result['status'],'unavailable')

    def test_dynamic_fact_is_uncertainty_not_a_proven_policy_mismatch(self):
        before={'knowledge/product-facts.json':json.dumps({'facts':{'price':'29'},'required_routes':{'price':['/pricing']}})}
        result=safeguards.policy_checks(before,{'demo-site/src/pages/pricing.astro':'<span data-fact="price">{price}</span>'})
        self.assertEqual(result['evidence'][0]['code'],'dynamic_fact_unverified')

    def test_invalid_policy_is_disclosed_as_unassessed(self):
        before={'knowledge/product-facts.json':json.dumps({'facts':{'price':'29'},'required_routes':{'price':123}})}
        self.assertEqual(safeguards.policy_checks(before,{})['status'],'not_assessed')
