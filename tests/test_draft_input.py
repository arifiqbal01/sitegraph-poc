"""Draft input scoping, immutable baselines, byte budgets and safe provider errors."""
import copy
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from api import ai, checkpoints, workspace, draft_context
import test_outcomes as outcomes
from test_outcomes import PRICING


class DraftInputTests(unittest.TestCase):
    def fixture(self):
        fixture = outcomes.OutcomeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def draft(self, fixture, report, edits):
        with patch.object(workspace, 'ROOT', fixture.root), \
             patch.object(workspace, 'SOURCE', fixture.root/'demo-site/src'), \
             patch.object(ai, 'plan', return_value={'entity':'Starter'}) as planner, \
             patch.object(ai, 'propose_edits', return_value={'edits':edits}) as editor:
            result = workspace.draft('Change only agreed content', report['change_id'])
        return result, planner, editor

    def test_contract_targets_only_and_full_rules_preserved(self):
        fixture = self.fixture()
        report = fixture.report()
        record = copy.deepcopy(checkpoints.load(report['change_id']))
        result, planner, editor = self.draft(fixture, report, [{'path':PRICING,'content':fixture.candidate()}])
        sent_files, context = editor.call_args.args[1:]
        self.assertEqual(list(sent_files), [PRICING])
        self.assertEqual(sent_files[PRICING], record['baseline'][PRICING])
        self.assertEqual(context['implementation_contract'], report['implementation_contract'])
        self.assertEqual(context['original_request'], report['original_request'])
        self.assertNotIn('mandatory_impact_context', context)
        self.assertNotIn('plan', context)
        self.assertEqual(checkpoints.load(report['change_id']), record)
        self.assertEqual(result['input_summary']['editable_files'], [PRICING])
        self.assertEqual([n['file'] for n in planner.call_args.args[1]['nodes']], [PRICING])

    def test_no_contract_multiple_targets_and_old_saved_report(self):
        fixture = self.fixture()
        changes = [{'target':route,'entity':'Starter','field':'monthly_price',
                    'old_value':'$29.90','new_value':'$19.90'} for route in ('/','/pricing','/faq')]
        report = checkpoints.analyze({'original_request':'Preserve colours and Growth; test pricing',
                                      'proposed_changes':changes})
        # Selection resolves proposals, not a new field absent from older saved reports.
        result, _, editor = self.draft(fixture, report, [{'path':PRICING,'content':fixture.candidate()}])
        self.assertEqual(set(editor.call_args.args[1]),
                         {'demo-site/src/pages/index.astro', PRICING, 'demo-site/src/pages/faq.astro'})
        self.assertEqual(editor.call_args.args[2]['proposed_changes'], changes)
        self.assertNotIn('implementation_contract', editor.call_args.args[2])
        self.assertTrue(editor.call_args.args[2]['policy_evidence'])

    def test_model_cannot_edit_a_related_page_outside_scope(self):
        fixture = self.fixture()
        report = fixture.report()
        with self.assertRaisesRegex(ValueError,'outside the supplied target scope'):
            self.draft(fixture, report, [{'path':'demo-site/src/pages/faq.astro',
                                         'content':'---\n---\n<h1>Unapproved</h1>'}])
        self.assertFalse(workspace.WORKSPACES.exists())

    def test_unknown_target_does_not_fall_back_to_whole_site(self):
        fixture = self.fixture()
        report = checkpoints.analyze({'proposed_changes':[{'target':'/unknown','field':'text'}]})
        with patch.object(ai, 'plan') as planner:
            with self.assertRaisesRegex(ValueError,'target must resolve'):
                self.draft(fixture,report,[])
            planner.assert_not_called()

    def test_preflight_oversize_calls_no_model(self):
        fixture = self.fixture()
        report = fixture.report()
        with patch.object(workspace,'ROOT',fixture.root), \
             patch.object(workspace,'SOURCE',fixture.root/'demo-site/src'), \
             patch.dict('os.environ',{'LLM_MAX_INPUT_BYTES':'100'}), \
             patch.object(ai,'plan') as planner, patch.object(ai,'propose_edits') as editor:
            with self.assertRaises(ai.ModelRequestError) as error:
                workspace.draft('Change CTA',report['change_id'])
            self.assertEqual(error.exception.detail['code'],'input_budget_exceeded')
            planner.assert_not_called()
            editor.assert_not_called()

    def test_optional_excerpts_trimmed_but_source_and_invariants_intact(self):
        context={'original_request':'preserve all features','implementation_contract':{'checks':['mandatory']},
                 'policy_evidence':[{'quote':'x'*5000} for _ in range(10)]}
        original=copy.deepcopy(context)
        with patch.dict('os.environ',{'LLM_MAX_INPUT_BYTES':'3000'}):
            payload, summary=ai.editor_payload('test',{'page':'complete source'},context)
        self.assertEqual(payload['files'],{'page':'complete source'})
        self.assertEqual(payload['impact_context']['implementation_contract'],context['implementation_contract'])
        self.assertLessEqual(summary['request_bytes'],3000)
        self.assertEqual(context,original)

    def test_unresolved_required_scope_stays_complete(self):
        with patch.dict('os.environ',{'LLM_MAX_INPUT_BYTES':'1000'}):
            with self.assertRaises(ai.ModelRequestError):
                ai.editor_payload('test',{'page':'required '*2000},{'policy_evidence':[]})


class ProviderErrorTests(unittest.TestCase):
    def test_editor_summary_matches_actual_wire_body(self):
        files={'demo-site/src/pages/index.astro':'complete source é'}
        context={'original_request':'preserve everything','policy_evidence':[]}
        _,summary=ai.editor_payload('edit',files,context)
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"edits":[]}'}}]}).encode())
        with patch.dict('os.environ',{'LLM_API_KEY':'private'}), \
             patch.object(ai.request,'urlopen',return_value=response) as transport:
            result=ai.propose_edits('edit',files,context)
        wire=transport.call_args.args[0].data
        self.assertEqual(len(wire),summary['request_bytes'])
        sent=json.loads(json.loads(wire)['messages'][1]['content'])
        self.assertEqual(sent['files'],files)
        self.assertEqual(result,{'edits':[]})

    def test_actual_serialized_utf8_request_is_bounded_before_transport(self):
        with patch.dict('os.environ',{'LLM_API_KEY':'private','LLM_MAX_INPUT_BYTES':'100'}), \
             patch.object(ai.request,'urlopen') as transport:
            with self.assertRaises(ai.ModelRequestError):
                ai.complete('system','é'*500)
            transport.assert_not_called()

    def test_413_and_429_safe_metadata_and_no_automatic_retry(self):
        for status, code in [(413,'provider_payload_too_large'),(429,'provider_rate_limited'),(500,'provider_error')]:
            with self.subTest(status=status):
                failure=HTTPError('https://provider.example/private',status,'secret error',
                                  {'Retry-After':'30'},io.BytesIO(b'private provider body'))
                with patch.dict('os.environ',{'LLM_API_KEY':'private','LLM_MAX_INPUT_BYTES':'24000'}), \
                     patch.object(ai.request,'urlopen',side_effect=failure) as transport:
                    with self.assertRaises(ai.ModelRequestError) as error:
                        ai.complete('system','request')
                self.assertEqual(error.exception.detail['code'],code)
                self.assertEqual(error.exception.detail['provider_status'],status)
                self.assertEqual(error.exception.detail['retry_after_seconds'],30)
                self.assertNotIn('private',json.dumps(error.exception.detail))
                self.assertEqual(transport.call_count,1)

    def test_http_returns_size_error_as_413_not_contract_422(self):
        from api.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as client, \
             patch.object(workspace,'draft',side_effect=ai.ModelRequestError('Input too large','input_budget_exceeded',413)):
            result=client.post('/ai/draft',json={'description':'test','change_id':'a'*32})
        self.assertEqual(result.status_code,413)
        self.assertEqual(result.json()['detail']['code'],'input_budget_exceeded')
