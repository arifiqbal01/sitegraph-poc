"""HTTP integration requires: pip install -r api/requirements.txt httpx."""
import unittest
from unittest.mock import patch
import test_outcomes as outcomes
from test_outcomes import PRICING, contract
from api import workspace
try:
    from api.main import app
    from fastapi.testclient import TestClient
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False

@unittest.skipUnless(API_AVAILABLE, 'Install API requirements and httpx for HTTP integration')
class HTTPWorkflowTests(unittest.TestCase):
    def test_contract_workflow_and_validation(self):
        fixture = outcomes.OutcomeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with TestClient(app) as client:
            self.assertEqual(client.get('/openapi.json').json()['info']['version'], '0.6.0')
            body = {'original_request': 'Improve Starter CTA, preserve price and facts',
                    'proposed_changes': [{'target': '/pricing', 'field': 'pricing_presentation'}],
                    'implementation_contract': contract()}
            response = client.post('/impact/analyze', json=body)
            self.assertEqual(response.status_code, 200, response.text)
            change_id = response.json()['change_id']
            with patch.object(workspace, 'ROOT', fixture.root), patch.object(workspace, 'SOURCE', fixture.root/'demo-site/src'), \
                 patch.object(workspace.ai, 'plan', return_value={'entity':'Starter'}), \
                 patch.object(workspace.ai, 'propose_edits', return_value={'edits':[{'path':PRICING, 'content':fixture.candidate()}]}):
                draft = client.post('/ai/draft', json={'description':'Apply saved contract', 'change_id':change_id})
                self.assertEqual(draft.status_code, 200, draft.text)
                draft_id = draft.json()['draft_id']
                self.assertEqual(client.post('/ai/apply', json={'draft_id':draft_id}).status_code, 200)
            verified = client.post('/impact/verify', json={'change_id':change_id, 'draft_id':draft_id})
            self.assertEqual(verified.status_code, 200, verified.text)
            self.assertEqual(verified.json()['decision'], 'no_detected_blockers', verified.text)
            for invalid in ({'allowed_edit_files':['../escape'], 'checks':[]},
                            {'allowed_edit_files':[PRICING], 'checks':[{'id':'bad', 'kind':[], 'file':PRICING}]}):
                with self.subTest(invalid=invalid):
                    self.assertEqual(client.post('/impact/analyze', json=dict(body, implementation_contract=invalid)).status_code, 422)
