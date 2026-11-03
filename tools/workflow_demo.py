"""Scripted model responses, real orchestration/verification. No live LLM required."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
from api import ai, checkpoints, suggestions, safeguards, workflow

PAGE = 'demo-site/src/pages/pricing.astro'


def run(case, rendered=True):
    source = (checkpoints.ROOT/PAGE).read_text()
    old_cta = '<a class="button" href="/faq">Starter plan questions</a>'
    new_cta = '<a class="button" href="/faq" style="background:#FFCED8;color:#81A6C6">Starter plan questions</a>'
    if case == 'correct':
        changes = [{'action':'update','target':'/pricing','entity':'Starter','field':'cta',
                    'old_value':'Starter plan questions','new_value':'Learn more about Starter','reason':'AI suggestion: clearer copy'}]
        candidate = source.replace('Starter plan questions','Learn more about Starter')
        checks = json.loads((checkpoints.ROOT/'scenarios/cta-contract.json').read_text())['implementation_contract']
    else:
        changes = [
            {'action':'update','target':'/pricing','entity':'Starter','field':'monthly_price','old_value':'$29.90','new_value':'$19.90','reason':'AI infers a cheaper price'},
            {'action':'update','target':'/pricing','entity':'Starter','field':'button_style','old_value':old_cta,'new_value':new_cta,'reason':'AI suggests pastel colours'},
            {'action':'update','target':'/pricing','entity':'Starter','field':'heading','old_value':'<h2 id="starter-heading">Starter</h2>','new_value':'<h4 id="starter-heading">Starter</h4>','reason':'AI suggests a smaller card heading'},
        ]
        candidate = source.replace('$29.90','$19.90').replace(old_cta,new_cta).replace('<h2 id="starter-heading">Starter</h2>','<h4 id="starter-heading">Starter</h4>')
        checks = None
    line = next(i for i,text in enumerate(source.splitlines(),1) if '<h1>' in text)
    raw = {'proposed_changes':changes,'source_evidence':[{'file':PAGE,'line':line,'quote':'Clear plans for growing teams'}],
           'preservation_suggestions':['Preserve Growth, features, CTA destination and policy files'],
           'assumptions':['These suggestions are not approved policy.'], 'clarification_questions':[],
           'verification_contract':checks}
    def model(system, data):
        if system == suggestions.SYSTEM:
            return raw
        if system == safeguards.REVIEW_SYSTEM:
            return {'findings':[], 'limitations':['Scripted reviewer response; this demo evaluates deterministic safeguards and actual browser checks.']}
        if system.startswith('You advise an independent website'):
            return {'intent':'Review the proposed changes independently','investigations':[], 'uncertainties':[]}
        if system == ai.EDITOR_SYSTEM:
            return {'edits':[{'path':PAGE,'content':candidate,'reason':'Follow AI suggestions exactly'}]}
        return {'entity':'Starter','affected_routes':['/pricing']}
    with patch.object(ai,'structured',side_effect=model):
        result = workflow.run('Make the Starter card clearer and more appealing.',run_rendered=rendered,run_ai_review=True)
    record_file = workflow._folder()/(result['workflow_id']+'.json')
    # Store explicit fixture provenance alongside the workflow, never claim live AI.
    result['model_provenance'] = 'scripted_fixture_no_live_provider'
    record_file.write_text(json.dumps(result,indent=2))
    verification = result['verification']
    runtime = verification['rendered_verification']
    codes = {e['code'] for e in runtime.get('evidence',[])}
    expected = 'no_detected_blockers' if case == 'correct' else 'review_required'
    valid = result['decision'] == expected and all(o['status']=='passed' for o in verification['outcome_checks'])
    if rendered:
        valid &= runtime['status'] not in {'not_run','unavailable'}
        if case == 'harmful':
            valid &= {'color-contrast','heading_level_skip','policy_mismatch'} <= codes
    print(json.dumps({'case':case,'workflow_id':result['workflow_id'],'model_provenance':result['model_provenance'],
                      'decision':result['decision'],'all_ai_proposal_outcomes_matched':all(o['status']=='passed' for o in verification['outcome_checks']),
                      'rendered_codes':sorted(codes),'validated':valid,'report':str(record_file)}),flush=True)
    return valid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=['correct','harmful','all'],default='all')
    args=parser.parse_args()
    results=[run(case) for case in (('correct','harmful') if args.case=='all' else (args.case,))]
    raise SystemExit(0 if all(results) else 1)

if __name__=='__main__': main()
