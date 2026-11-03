"""Model-output variations retain intent; protocol repair is not policy approval."""
import copy
import json
import unittest
from unittest.mock import patch
from api import ai, suggestions, checkpoints as cp, workspace, reasoning
import test_outcomes as outcomes
import test_workflow as examples
from test_outcomes import PRICING


class SuggestionParserTests(unittest.TestCase):
    def setUp(self):
        self.fixture=outcomes.OutcomeTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.raw=examples.raw_proposal(self.fixture)

    def parse(self, raw=None):
        with patch.object(ai,'structured',return_value=raw or self.raw):
            return suggestions.propose('Improve Starter')

    def test_null_optional_values_do_not_reject_entire_proposal(self):
        self.raw['proposed_changes'][0].update(old_value=None,new_value=None)
        result=self.parse()['proposed_changes'][0]
        self.assertNotIn('old_value',result)
        self.assertNotIn('new_value',result)
        self.assertEqual(result['additional_context']['original_values'],{'old_value':None,'new_value':None})

    def test_extra_risky_suggestions_preserved_without_rewriting(self):
        risky={'background':'#FFCED8','color':'#81A6C6','price':19.9}
        self.raw['proposed_changes'][0]['styles_and_price']=risky
        result=self.parse()['proposed_changes'][0]
        self.assertEqual(result['additional_context']['extra_fields']['styles_and_price'],risky)
        self.assertEqual(result['provenance'],'ai_suggestion')

    def test_numeric_and_boolean_literals_retain_original_types(self):
        self.raw['proposed_changes'][0].update(old_value=29.9,new_value=19.9)
        result=self.parse()['proposed_changes'][0]
        self.assertEqual(result['old_value'],'29.9')
        self.assertEqual(result['new_value'],'19.9')
        self.assertEqual(result['additional_context']['original_values']['new_value'],19.9)
        self.raw['proposed_changes'][0].update(old_value=True,new_value=False)
        self.assertEqual(self.parse()['proposed_changes'][0]['new_value'],'false')

    def test_structured_values_are_context_not_fake_literal_checks(self):
        value={'background':'#FFCED8','text':'#81A6C6'}
        self.raw['proposed_changes'][0].update(new_value=value)
        result=self.parse()['proposed_changes'][0]
        self.assertNotIn('new_value',result)
        self.assertEqual(result['additional_context']['original_values']['new_value'],value)

    def test_empty_text_is_preserved_as_an_intentional_removal(self):
        self.raw['proposed_changes'][0]['new_value']=''
        self.assertEqual(self.parse()['proposed_changes'][0]['new_value'],'')

    def test_common_aliases_and_source_path_resolve_to_same_page(self):
        self.raw['proposed_changes']=[{'operation':'edit','file':'src/pages/pricing.astro',
            'element':'Starter CTA','type':'cta','description':'Clarify wording','from':None,'to':'Learn more about Starter'}]
        result=self.parse()['proposed_changes'][0]
        self.assertEqual(result['target'],'/pricing')
        self.assertEqual(result['action'],'update')
        self.assertEqual(result['reason'],'Clarify wording')
        self.assertEqual(result['new_value'],'Learn more about Starter')
        self.assertEqual(result['additional_context']['extra_fields']['operation'],'edit')

    def test_unknown_and_conflicting_targets_are_precise_errors(self):
        self.raw['proposed_changes'][0]['target']='/missing'
        with self.assertRaisesRegex(ValueError,r'proposed_changes\[0\].target:'):
            self.parse()
        self.raw['proposed_changes'][0].update(target='/pricing',file='src/pages/faq.astro')
        with self.assertRaisesRegex(ValueError,'conflicts with file'):
            self.parse()

    def test_missing_metadata_is_disclosed_and_unsupported_operations_rejected(self):
        for field in ('entity','field','reason'):
            raw=copy.deepcopy(self.raw);raw['proposed_changes'][0][field]=None
            with self.subTest(field=field):
                result=self.parse(raw)['proposed_changes'][0]
                self.assertIsNone(result['additional_context']['original_values'][field])
                self.assertTrue(result['additional_context']['normalization_notes'])
        self.raw['proposed_changes'][0]['action']='delete'
        with self.assertRaisesRegex(ValueError,'unsupported operation'):
            self.parse()

    def test_optional_context_lists_accept_null_string_and_objects(self):
        self.raw['preservation_suggestions']=None
        self.raw['assumptions']='AI inferred this; not approved'
        question={'question':'What price?','reason':'No business direction supplied'}
        self.raw['clarification_questions']=[question]
        context=self.parse()['suggestion_context']
        self.assertEqual(context['preservation_suggestions'],[])
        self.assertEqual(context['assumptions'],['AI inferred this; not approved'])
        self.assertEqual(json.loads(context['clarification_questions'][0]),question)

    def test_extra_proposal_context_and_model_provenance_not_blessed(self):
        self.raw['risks']=['Policy may conflict']
        self.raw['proposed_changes'][0]['provenance']='human_approved'
        result=self.parse();change=result['proposed_changes'][0]
        self.assertEqual(change['provenance'],'ai_suggestion')
        self.assertEqual(change['additional_context']['extra_fields']['provenance'],'human_approved')
        self.assertEqual(change['additional_context']['proposal_extra_fields']['risks'],['Policy may conflict'])
        self.assertIsNone(result['implementation_contract'])

    def test_limits_and_evidence_validation_remain_enforced(self):
        raw=copy.deepcopy(self.raw);raw['proposed_changes'][0]['notes']='x'*17000
        with self.assertRaisesRegex(ValueError,'context limit'):
            self.parse(raw)
        raw=copy.deepcopy(self.raw);raw['source_evidence'][0]['quote']='invented'
        with self.assertRaisesRegex(ValueError,'supplied source'):
            self.parse(raw)
        raw=copy.deepcopy(self.raw);raw['proposed_changes'][0]['new_value']=float('nan')
        with self.assertRaisesRegex(ValueError,'finite JSON'):
            self.parse(raw)

    def test_http_workflow_consumes_normalized_output_and_carries_extras(self):
        from api.main import app
        from fastapi.testclient import TestClient
        self.raw['proposed_changes'][0].update(old_value=None,notes={'preserve':'/faq'})
        def model(system,data):
            if system==suggestions.SYSTEM:return self.raw
            if system==ai.EDITOR_SYSTEM:
                self.assertEqual(data['impact_context']['proposed_changes'][0]['additional_context']['extra_fields']['notes'],{'preserve':'/faq'})
                return {'edits':[{'path':PRICING,'content':self.fixture.candidate()}]}
            return {'entity':'Starter'}
        with patch.object(ai,'structured',side_effect=model), \
             patch.object(workspace,'ROOT',self.fixture.root),patch.object(workspace,'SOURCE',self.fixture.root/'demo-site/src'), \
             TestClient(app) as client:
            response=client.post('/workflow/run',json={'prompt':'Improve Starter','run_rendered':False,'run_ai_review':False})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'ready_for_human_review')
        self.assertTrue(response.json()['draft_id'])
        self.assertEqual(response.json()['decision'],'review_required')

    def test_equivalent_action_aliases_do_not_create_false_conflicts(self):
        self.raw['proposed_changes'][0].update(action='update',operation='edit')
        self.assertEqual(self.parse()['proposed_changes'][0]['action'],'update')

    def test_conflicting_substantive_values_are_not_silently_chosen(self):
        self.raw['proposed_changes'][0].update(new_value='A',to='B')
        with self.assertRaisesRegex(ValueError,r'proposed_changes\[0\].new_value: conflicts with to'):
            self.parse()
