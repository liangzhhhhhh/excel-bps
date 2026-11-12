"""Build/test the BPS panel, then replace only the existing Manager service.

Uses the exact current Manager image as the backend base. Does not rebuild CPA,
change API keys or edit the original downloaded source. Requires Docker Compose.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

CONTAINER = 'cpamp-cpa-manager-plus-1'
ROOT = Path(__file__).resolve().parents[1]

def run(args, capture=False):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None).stdout

def inspect(name):
    return json.loads(run(['docker', 'inspect', name], True))[0]

def main():
    before = inspect(CONTAINER)
    labels = before['Config'].get('Labels') or {}
    service = labels.get('com.docker.compose.service')
    project = labels.get('com.docker.compose.project')
    if not service or not project:
        raise RuntimeError('Unexpected Compose service/project; nothing changed')
    files = [Path(p) for p in labels.get('com.docker.compose.project.config_files', '').split(',') if p]
    if not files or not all(p.is_absolute() and p.is_file() for p in files):
        raise RuntimeError('Cannot resolve original Compose files; nothing changed')
    if not any(m.get('Destination') == '/data' for m in before.get('Mounts', [])):
        raise RuntimeError('Expected persistent /data mount is missing; nothing changed')
    old_image = before['Image']
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    base_tag = 'local/cpamp-bps-base:' + old_image.split(':')[-1][:16]
    new_tag = 'local/cpamp-bps-panel:0.5.31-' + timestamp
    run(['docker', 'tag', old_image, base_tag])
    # All checks finish before creating an override or replacing any service.
    run(['docker', 'build', '--file', str(ROOT / 'Dockerfile.bps-panel'),
         '--build-arg', 'MANAGER_BASE=' + base_tag, '--tag', new_tag, str(ROOT)])
    built = inspect(new_tag)
    if built['Config'].get('Entrypoint') != before['Config'].get('Entrypoint'):
        raise RuntimeError('Backend entrypoint changed; refusing to install')
    override = files[0].parent / ('compose.bps-panel-' + timestamp + '.json')
    rollback = files[0].parent / ('compose.bps-panel-rollback-' + timestamp + '.json')
    panel_path = '/opt/cpa-bps/management.html'
    old_env = dict(item.split('=', 1) for item in before['Config'].get('Env', []) if '=' in item)
    override.write_text(json.dumps({'services': {service: {'image': new_tag, 'environment': {'PANEL_PATH': panel_path}}}}, indent=2), encoding='utf-8')
    rollback.write_text(json.dumps({'services': {service: {'image': base_tag, 'environment': {'PANEL_PATH': old_env.get('PANEL_PATH', '')}}}}, indent=2), encoding='utf-8')
    os.chmod(override, 0o600)
    os.chmod(rollback, 0o600)
    base = ['docker', 'compose', '-p', project]
    working_dir = labels.get('com.docker.compose.project.working_dir')
    if working_dir:
        base += ['--project-directory', working_dir]
    for path in files:
        base += ['-f', str(path)]
    apply = base + ['-f', str(override), 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', service]
    undo = base + ['-f', str(rollback), 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', service]
    try:
        run(apply)
        for _ in range(30):
            after = inspect(CONTAINER)
            state = after.get('State', {})
            if state.get('Status') == 'running' and state.get('Health', {}).get('Status', 'healthy') == 'healthy':
                break
            time.sleep(2)
        else:
            raise RuntimeError('Manager did not become healthy')
        if after['Image'] != built['Id']:
            raise RuntimeError('Unexpected running Manager image')
        old_mounts = {(m['Source'], m['Destination']) for m in before.get('Mounts', [])}
        new_mounts = {(m['Source'], m['Destination']) for m in after.get('Mounts', [])}
        if old_mounts != new_mounts:
            raise RuntimeError('Persistent mounts changed')
    except Exception:
        print('Manager replacement failed; restoring previous image.')
        run(undo)
        raise
    commands = '\n'.join([
        'BPS panel installed; refresh the browser with Ctrl+F5.',
        'For future Compose recreation, include this additional override:',
        shlex.join(base + ['-f', str(override)]),
        'Rollback:', shlex.join(undo), '',
    ])
    (ROOT / 'BPS-PANEL-INSTALL-RESULT.txt').write_text(commands, encoding='utf-8')
    print(commands)

if __name__ == '__main__':
    main()
