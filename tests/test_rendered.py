"""Deterministic staging and fail-closed integration; real browser exercised by demo CI."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api import rendered, checkpoints as cp
import test_outcomes as outcomes
from test_outcomes import PRICING
from tools.demo import candidate


class SnapshotTests(unittest.TestCase):
    def test_support_files_frozen_and_candidate_pages_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            src=root/'demo-site/src'
            (src/'layouts').mkdir(parents=True)
            (src/'pages').mkdir()
            (src/'layouts/Base.astro').write_text('original layout')
            (src/'pages/index.astro').write_text('original page')
            (root/'demo-site/package.json').write_text('{}')
            frozen=rendered.snapshot(root)
            (src/'layouts/Base.astro').write_text('modified after analysis')
            preview=root/'preview';preview.mkdir()
            (preview/'index.astro').write_text('candidate page')
            baseline={'demo-site/src/pages/index.astro':'saved page'}
            rendered.stage(frozen,baseline,None,root/'base')
            rendered.stage(frozen,baseline,preview,root/'candidate')
            self.assertEqual((root/'base/src/pages/index.astro').read_text(),'saved page')
            self.assertEqual((root/'candidate/src/pages/index.astro').read_text(),'candidate page')
            self.assertEqual((root/'candidate/src/layouts/Base.astro').read_text(),'original layout')
            self.assertEqual((src/'pages/index.astro').read_text(),'original page')

    def test_old_analysis_cannot_silently_use_current_layout(self):
        result=rendered.verify({'baseline':{}},Path('/unused'),[])
        self.assertEqual(result['status'],'unavailable')

    def test_snapshot_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                rendered.stage({'files':{'../escape':'00'}},{},None,Path(temp))

    def test_fixtures_target_distinct_failures(self):
        content=Path('demo-site/src/pages/pricing.astro').read_text()
        self.assertIn('href="/services/seo"',candidate(content,'wrong-destination'))
        self.assertIn('robots="noindex,follow"',candidate(content,'seo-noindex'))
        self.assertIn('tabindex="-1"',candidate(content,'inaccessible-cta'))
        self.assertIn('data-fact="starter-seats">30<',candidate(content,'fact-drift'))
        self.assertNotIn('Starter plan questions',candidate(content,'correct'))


class RenderedDecisionTests(unittest.TestCase):
    def fixture(self):
        fixture=outcomes.OutcomeTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        report=fixture.report()
        fixture.verify(report,{PRICING:fixture.candidate()})
        return report

    def test_unavailable_browser_requires_review(self):
        report=self.fixture()
        with patch.object(rendered,'verify',return_value={'status':'unavailable','detail':'Browser not installed'}):
            result=cp.verify(report['change_id'],'a'*32,run_rendered=True)
        self.assertEqual(result['decision'],'review_required')
        self.assertIn('Rendered verification: unavailable',result['human_report']['requires_review'])

    def test_browser_failure_cannot_be_hidden_by_source_pass(self):
        report=self.fixture()
        with patch.object(rendered,'verify',return_value={'status':'review_required','evidence':[{'domain':'seo','code':'noindex','route':'/pricing'}]}):
            result=cp.verify(report['change_id'],'a'*32,run_rendered=True)
        self.assertEqual(result['decision'],'review_required')
        self.assertEqual(result['rendered_verification']['evidence'][0]['code'],'noindex')

    def test_completed_browser_keeps_source_decision(self):
        report=self.fixture()
        with patch.object(rendered,'verify',return_value={'status':'completed','evidence':[]}):
            result=cp.verify(report['change_id'],'a'*32,run_rendered=True)
        self.assertEqual(result['decision'],'no_detected_blockers')
        self.assertFalse(any(x['check']=='rendered_accessibility' and x['status']=='not_run' for x in result['investigation_results']))

    def test_completed_browser_cannot_override_failed_contract(self):
        report=self.fixture()
        from api import workspace
        preview=workspace.WORKSPACES/('a'*32)/'preview/pages/pricing.astro'
        preview.write_text(preview.read_text().replace('Learn more about Starter','Unapproved text'))
        with patch.object(rendered,'verify',return_value={'status':'completed','evidence':[]}):
            result=cp.verify(report['change_id'],'a'*32,run_rendered=True)
        self.assertEqual(result['decision'],'review_required')

    def test_fact_failure_does_not_mislabel_accessibility(self):
        report=self.fixture()
        runtime={'status':'review_required','evidence':[], 'domain_results':{
            'seo':{'status':'completed'},'accessibility':{'status':'completed'},'facts':{'status':'review_required'}}}
        with patch.object(rendered,'verify',return_value=runtime):
            result=cp.verify(report['change_id'],'a'*32,run_rendered=True)
        self.assertEqual(result['decision'],'review_required')
        item=next(x for x in result['investigation_results'] if x['check']=='rendered_accessibility')
        self.assertEqual(item['status'],'completed')
