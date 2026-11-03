"""Reproducible isolated candidates: python -m tools.demo --rendered.

Creates fresh analysis/draft IDs; never calls a model, edits original sources,
relaxes a contract, or overwrites another candidate.
"""
import argparse
import json
import uuid
from pathlib import Path
from api import checkpoints, workspace

CASES = ('correct', 'wrong-destination', 'seo-noindex', 'inaccessible-cta', 'fact-drift')
PAGE = 'demo-site/src/pages/pricing.astro'


def candidate(content, case):
    content = content.replace('Starter plan questions', 'Learn more about Starter')
    if case == 'wrong-destination':
        content = content.replace('class="button" href="/faq"', 'class="button" href="/services/seo"')
    elif case == 'seo-noindex':
        content = content.replace('<Base title=', '<Base robots="noindex,follow" title=', 1)
    elif case == 'inaccessible-cta':
        content = content.replace('class="button" href="/faq"', 'class="button" href="/faq" tabindex="-1" style="color:#fff;background:#fff"')
    elif case == 'fact-drift':
        content = content.replace('data-fact="starter-seats">3<', 'data-fact="starter-seats">30<')
    return content


def run(case, rendered=False):
    request = json.loads((checkpoints.ROOT/'scenarios/cta-contract.json').read_text())
    request['use_ai'] = False
    request['original_request'] += ' Preserve SEO metadata, accessibility and supplied product facts.'
    report = checkpoints.analyze(request)
    record = checkpoints.load(report['change_id'])
    draft_id = uuid.uuid4().hex
    folder = workspace.WORKSPACES/draft_id
    folder.mkdir(parents=True)
    after = candidate(record['baseline'][PAGE], case)
    proposal = {'change_id':report['change_id'], 'implementation_contract':report['implementation_contract'],
                'description':'Deterministic demo fixture: '+case,
                'provenance':{'kind':'deterministic_fixture','case':case,'model_called':False},
                'edits':[{'path':PAGE,'before':record['baseline'][PAGE],'after':after,'reason':'Labelled demonstration fixture'}]}
    (folder/'proposal.json').write_text(json.dumps(proposal,indent=2))
    workspace.apply(draft_id)
    result = checkpoints.verify(report['change_id'], draft_id, run_rendered=rendered)
    (folder/'verification.json').write_text(json.dumps(result,indent=2))
    expected = 'no_detected_blockers' if case == 'correct' else 'review_required'
    runtime = result['rendered_verification']
    codes = sorted({e['code'] for e in runtime.get('evidence',[])})
    required = {'seo-noindex':'noindex','inaccessible-cta':'cta_keyboard_unreachable','fact-drift':'policy_mismatch'}
    validated = result['decision'] == expected
    if case == 'wrong-destination':
        validated = validated and any(c['id']=='starter-cta-destination' and c['status']=='failed' for c in result['contract_checks'])
    if rendered:
        validated = validated and runtime['status'] not in {'unavailable','not_run'}
        if case in required:
            validated = validated and required[case] in codes
    return {'case':case,'change_id':report['change_id'],'draft_id':draft_id,'expected':expected,
            'observed':result['decision'],'rendered_status':runtime['status'],'rendered_codes':codes,
            'validated':validated,'report':str(folder/'verification.json')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES+('all',),default='all')
    parser.add_argument('--rendered', action='store_true')
    args=parser.parse_args()
    results=[]
    for case in CASES if args.case=='all' else (args.case,):
        result=run(case,args.rendered)
        print(json.dumps(result),flush=True)
        results.append(result)
    raise SystemExit(0 if all(r['validated'] for r in results) else 1)

if __name__=='__main__':main()
