"""One prompt through isolated verification; human review is the final step."""
import json
import re
import uuid
from . import ai, checkpoints, suggestions, workspace


class WorkflowFailure(Exception):
    def __init__(self, status_code, record):
        self.status_code = status_code
        self.record = record


def _folder():
    return checkpoints.STORE.parent / 'workflows'


def _save(record):
    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (record['workflow_id'] + '.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path)


def load(ident):
    if not re.fullmatch('[a-f0-9]{32}', ident):
        raise ValueError('Invalid workflow ID')
    path = _folder() / (ident + '.json')
    if not path.is_file():
        raise ValueError('Unknown workflow ID')
    return json.loads(path.read_text())


def run(prompt, run_rendered=True, run_ai_review=True):
    record = {'workflow_id': uuid.uuid4().hex, 'status': 'running', 'stage': 'suggestions',
              'human_prompt': prompt, 'human_review': 'not_yet_reviewed', 'published': False}
    _save(record)
    try:
        record['proposal'] = suggestions.propose(prompt)
        record['stage'] = 'analysis'
        _save(record)
        record['analysis'] = checkpoints.analyze(dict(record['proposal'], use_ai=run_ai_review))
        record['change_id'] = record['analysis']['change_id']
        record['stage'] = 'draft'
        _save(record)
        record['draft'] = workspace.draft(prompt, change_id=record['change_id'])
        record['draft_id'] = record['draft']['draft_id']
        record['stage'] = 'isolated_apply'
        _save(record)
        # The caller of this endpoint explicitly requests the entire isolated flow.
        # No original website write, external publication or proposal approval occurs.
        record['preview'] = workspace.apply(record['draft_id'])
        record['stage'] = 'verification'
        _save(record)
        record['verification'] = checkpoints.verify(record['change_id'], record['draft_id'],
                                                   run_rendered=run_rendered, run_ai_review=run_ai_review)
        if not run_rendered or not run_ai_review:
            record['verification']['decision'] = 'review_required'
            record['verification']['human_report']['decision'] = 'review_required'
            record['verification']['human_report']['requires_review'].append('Workflow safeguard coverage reduced: a requested default check was disabled')
        record['status'] = 'ready_for_human_review'
        record['stage'] = 'human_review'
        record['decision'] = record['verification']['decision']
        verification = record['verification']
        record['review_summary'] = {
            'decision': record['decision'],
            'changed_files': verification['changed_files'],
            'verified': verification['human_report']['verified'],
            'requires_review': list(dict.fromkeys(verification['human_report']['requires_review'])),
            'assumptions': record['proposal']['suggestion_context']['assumptions'],
            'unanswered_questions': record['proposal']['suggestion_context']['clarification_questions'],
            'coverage': verification['coverage'],
            'limitations': list(dict.fromkeys(verification['human_report']['not_assessed'])),
            'expectation_provenance': verification['expectation_provenance'],
            'note': 'Matching AI expectations does not establish business or website safety. Review the diff and independent evidence.'
        }
        _save(record)
        return record
    except Exception as exc:
        record['status'] = 'failed'
        if isinstance(exc, ai.ModelRequestError):
            record['error'] = exc.detail
            status = exc.status_code
        else:
            # Keep partial IDs/evidence, without relaying arbitrary provider errors.
            record['error'] = {'code': 'workflow_stage_failed',
                               'message': str(exc) if isinstance(exc, ValueError) else 'Workflow stage failed; inspect local logs.'}
            status = 422 if isinstance(exc, ValueError) else 500
        _save(record)
        raise WorkflowFailure(status, record) from None
