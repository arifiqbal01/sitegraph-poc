"""Opt-in local build/browser verification of immutable, separately staged sources.

Builds execute repository code. Intended for this trusted local POC, not an
untrusted public build service. Never fetch arbitrary URLs or publish artifacts.
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def snapshot(root):
    site = root / 'demo-site'
    files = {}
    for folder in ('src', 'public'):
        for path in sorted((site / folder).rglob('*')):
            if path.is_file():
                files[path.relative_to(site).as_posix()] = path.read_bytes().hex()
    for name in ('package.json', 'package-lock.json', 'astro.config.mjs'):
        path = site / name
        if path.is_file():
            files[name] = path.read_bytes().hex()
    facts = root / 'knowledge/product-facts.json'
    return {'files': files, 'facts': json.loads(facts.read_text()) if facts.is_file() else None}


def stage(snapshot_data, baseline, preview, destination):
    """Use saved support files, never today's layout/config/assets as the baseline."""
    for name, encoded in snapshot_data['files'].items():
        target = destination / name
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Invalid render snapshot path')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes.fromhex(encoded))
    pages = destination / 'src/pages'
    if pages.exists():
        shutil.rmtree(pages)
    pages.mkdir(parents=True)
    if preview is not None:
        shutil.copytree(preview, pages, dirs_exist_ok=True)
    else:
        for path, content in baseline.items():
            if path.startswith('demo-site/src/pages/'):
                target = pages / path.removeprefix('demo-site/src/pages/')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)


def verify(record, preview, routes):
    frozen = record.get('render_snapshot')
    if not frozen or not frozen.get('files'):
        return {'status': 'unavailable', 'detail': 'Analysis predates rendered snapshots; create a new analysis.'}
    deps = ROOT / 'demo-site/node_modules'
    runner_deps = ROOT / 'tools/node_modules'
    if not (deps / '.bin/astro').exists() or not runner_deps.exists():
        return {'status': 'unavailable', 'detail': 'Install demo-site and tools dependencies plus Playwright Chromium; see docs/rendered-demo.md.'}
    # The installed dependency tree must correspond to the saved lockfile.
    lock = ROOT / 'demo-site/package-lock.json'
    if not lock.is_file() or frozen['files'].get('package-lock.json') != lock.read_bytes().hex():
        return {'status': 'unavailable', 'detail': 'Saved dependency lock differs from local install definition; restore matching dependencies.'}
    with tempfile.TemporaryDirectory(prefix='sitegraph-render-') as temp:
        folder = Path(temp)
        builds = []
        for label, candidate in (('baseline', None), ('candidate', preview)):
            project = folder / label
            stage(frozen, record['baseline'], candidate, project)
            (project / 'node_modules').symlink_to(deps, target_is_directory=True)
            try:
                result = subprocess.run(['node', str(deps / 'astro/astro.js'), 'build', '--root', str(project)],
                                        cwd=project, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.TimeoutExpired):
                return {'status': 'unavailable', 'detail': label + ' build could not complete', 'builds': builds}
            builds.append({'artifact': label, 'status': 'passed' if result.returncode == 0 else 'failed'})
            if result.returncode:
                return {'status': 'review_required', 'detail': label + ' Astro build failed; browser checks not run.', 'builds': builds}
        config = folder / 'audit.json'
        config.write_text(json.dumps({'baseline': str(folder/'baseline/dist'), 'candidate': str(folder/'candidate/dist'),
                                      'routes': sorted(set(routes)), 'facts': frozen.get('facts')}))
        try:
            result = subprocess.run(['node', str(ROOT/'tools/audit.mjs'), str(config)], cwd=ROOT,
                                    capture_output=True, text=True, timeout=180)
            if result.returncode:
                return {'status': 'unavailable', 'detail': 'Browser runner failed; install matching Chromium and system dependencies.', 'builds': builds}
            report = json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return {'status': 'unavailable', 'detail': 'Browser runner did not return a complete report.', 'builds': builds}
    report['builds'] = builds
    report['snapshot_sha256'] = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    return report
