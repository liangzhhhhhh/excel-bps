"""Install/upgrade BPS on existing Docker Compose CPA, without deploying CPA."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
HOST_TIMEZONE = Path('/etc/localtime')


def verify_binary_bundle():
    """Validate all shipped files before any Docker or deployment operation."""
    manifest = ROOT / 'BINARY.json'
    if not manifest.is_file():
        return False
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('format') != 1 or data.get('platform') != 'linux/amd64':
        raise RuntimeError('Unsupported binary bundle manifest.')
    entries = data.get('files')
    required = {'install.sh', 'plugin/dist/cpa-bps.so', 'plugin/dist/bps-config',
                'plugin/dist/native-smoke', 'plugin/dist/SHA256SUMS',
                'plugin/scripts/check-library.sh', 'plugin/scripts/install-unified.py',
                'panel/scripts/upgrade-bps-panel.py', 'panel/Dockerfile.bps-panel',
                'panel/apps/web/dist/index.html'}
    if not isinstance(entries, dict) or not required.issubset(entries):
        raise RuntimeError('Incomplete binary bundle.')
    for name, digest in entries.items():
        path = ROOT / name
        if '\\' in name or Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('Invalid binary bundle path.')
        if not path.resolve().is_relative_to(ROOT.resolve()) or path.is_symlink():
            raise RuntimeError('Invalid binary bundle file.')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Binary bundle integrity check failed: ' + name)
    print('Binary bundle SHA256 checks passed:', data.get('version'))
    return True


def run(args, capture=False, data=None, cwd=None):
    return subprocess.run(args, input=data, check=True, stdout=subprocess.PIPE if capture else None,
                          cwd=cwd).stdout


def inspect(name):
    return json.loads(run(['docker', 'inspect', name], True))[0]


def choose(containers, explicit, service):
    if explicit:
        return inspect(explicit)
    found = [c for c in containers if (c['Config'].get('Labels') or {}).get('com.docker.compose.service') == service]
    if len(found) != 1:
        raise RuntimeError('Cannot select exactly one ' + service + '; specify its container using --cpa-container or --manager-container.')
    return found[0]


def compose_context(info):
    labels = info['Config'].get('Labels') or {}
    project, service = labels.get('com.docker.compose.project'), labels.get('com.docker.compose.service')
    files = [Path(p) for p in labels.get('com.docker.compose.project.config_files', '').split(',') if p]
    if not project or not service or not files or not all(p.is_absolute() and p.is_file() for p in files):
        raise RuntimeError('Existing Docker Compose metadata/files are required; nothing changed.')
    base = ['docker', 'compose', '-p', project]
    work = labels.get('com.docker.compose.project.working_dir')
    if work:
        base += ['--project-directory', work]
    for f in files:
        base += ['-f', str(f)]
    return service, files, base


def write(path, data, mode=0o600):
    fd, tmp = tempfile.mkstemp(prefix='.bps-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def wait_running(name, image):
    for _ in range(30):
        current = inspect(name)
        state = current.get('State', {})
        if state.get('Running') and not state.get('Restarting') and state.get('Health', {}).get('Status', 'healthy') == 'healthy':
            if current['Image'] != image:
                raise RuntimeError('CPA image unexpectedly changed.')
            return current
        time.sleep(2)
    raise RuntimeError('CPA did not become healthy.')


def sync_timezone(cpa):
    mounts = [m for m in cpa.get('Mounts', []) if m.get('Destination') == '/CLIProxyAPI/plugins']
    if len(mounts) != 1 or mounts[0].get('Type') != 'bind' or not mounts[0].get('RW', True):
        raise RuntimeError('Install BPS first; expected writable plugin bind mount is missing.')
    data = HOST_TIMEZONE.read_bytes()
    if not data.startswith(b'TZif'):
        raise RuntimeError('Host timezone file is invalid.')
    write(Path(mounts[0]['Source']) / 'cpa-bps-localtime', data, 0o644)
    print('Server timezone synchronized. Effective on the next request; no restart required.')


def install(cpa, binary=False):
    name = cpa['Name'].lstrip('/')
    service, files, base = compose_context(cpa)
    mounts = {m['Destination']: m for m in cpa.get('Mounts', [])}
    config_mount = mounts.get('/CLIProxyAPI/config.yaml', {})
    if config_mount.get('Type') != 'bind' or not Path(config_mount.get('Source', '')).is_file():
        raise RuntimeError('CPA must bind-mount /CLIProxyAPI/config.yaml from a host file.')
    config = Path(config_mount['Source'])
    plugin_mount = mounts.get('/CLIProxyAPI/plugins')
    if plugin_mount and (plugin_mount.get('Type') != 'bind' or not plugin_mount.get('RW', True)):
        raise RuntimeError('Existing plugins mount must be a writable host bind directory.')
    directory = Path(plugin_mount['Source']) if plugin_mount else config.parent / 'plugins'
    if config.is_symlink() or directory.is_symlink():
        raise RuntimeError('Config/plugin symlinks require manual installation.')
    timezone = HOST_TIMEZONE.read_bytes()
    if not timezone.startswith(b'TZif'):
        raise RuntimeError('Host /etc/localtime is not a TZif timezone file.')
    run(base + ['config', '--quiet'])
    plugin = ROOT / 'plugin'
    if not binary:
        run(['sh', 'scripts/build-ubuntu.sh'], cwd=plugin)
    run(['sh', 'scripts/check-library.sh', name], cwd=plugin)
    dist = plugin / 'dist'
    os.chmod(dist / 'bps-config', 0o755)
    original = config.read_bytes()
    updated = run(['docker', 'run', '--rm', '-i', '--network', 'none', '--read-only',
                   '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '65534:65534',
                   '--memory', '128m', '--pids-limit', '32',
                   '--mount', 'type=bind,src=' + str(dist) + ',dst=/check,readonly',
                   '--entrypoint', '/check/bps-config', cpa['Image']], True, original)
    # All configuration/build checks precede production file changes.
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / '.bps-install.lock'
    lock.mkdir()
    try:
        backup = Path(tempfile.mkdtemp(prefix='bps-backup-', dir=str(files[0].parent)))
        os.chmod(backup, 0o700)
        config_mode = config.stat().st_mode & 0o777
        write(backup / 'config.yaml', original, config_mode)
        targets = [directory / 'cpa-bps.so', directory / 'cpa-bps-localtime']
        saved = [(p, p.read_bytes() if p.exists() else None, p.stat().st_mode & 0o777 if p.exists() else 0o644) for p in targets]
        for p, data, mode in saved:
            if data is not None:
                write(backup / p.name, data, mode)
        tag = 'local/cpa-bps-host:' + cpa['Image'].split(':')[-1][:16]
        run(['docker', 'tag', cpa['Image'], tag])
        override = backup / 'compose.bps.json'
        rollback = backup / 'compose.rollback.json'
        volumes = [{'type': 'bind', 'source': str(directory), 'target': '/CLIProxyAPI/plugins'}]
        write(override, json.dumps({'services': {service: {'image': tag, 'volumes': volumes}}}).encode())
        write(rollback, json.dumps({'services': {service: {'image': tag}}}).encode())
        up = ['up', '-d', '--force-recreate', '--no-deps', '--no-build', '--pull', 'never', service]
        apply = base + ['-f', str(override)] + up
        undo = base + ['-f', str(rollback)] + up
        run(base + ['-f', str(override), 'config', '--quiet'])
        commands = ['#!/bin/sh', 'set -eu', 'cp -p ' + shlex.quote(str(backup / 'config.yaml')) + ' ' + shlex.quote(str(config))]
        for p, data, mode in saved:
            commands.append(('cp -p ' + shlex.quote(str(backup / p.name)) + ' ' + shlex.quote(str(p))) if data is not None else 'rm -f ' + shlex.quote(str(p)))
        commands.append(shlex.join(undo))
        write(backup / 'rollback.sh', ('\n'.join(commands) + '\n').encode(), 0o700)
        try:
            write(targets[0], (dist / 'cpa-bps.so').read_bytes(), 0o644)
            write(targets[1], timezone, 0o644)
            write(config, updated, config_mode)
            run(apply)
            after = wait_running(name, cpa['Image'])
            previous_mounts = {(m['Source'], m['Destination']) for m in cpa.get('Mounts', [])}
            current_mounts = {(m['Source'], m['Destination']) for m in after.get('Mounts', [])}
            if not previous_mounts.issubset(current_mounts):
                raise RuntimeError('Existing CPA mounts changed.')
        except Exception:
            print('Installation failed; restoring CPA. Backup:', backup)
            run(['sh', str(backup / 'rollback.sh')])
            raise
        result = '\n'.join(['BPS plugin installed. Existing CPA image retained.',
                            'Compose command for future recreation:', shlex.join(base + ['-f', str(override)]),
                            'Rollback:', 'sh ' + shlex.quote(str(backup / 'rollback.sh')),
                            'Timezone synchronized from host /etc/localtime.', ''])
        write(ROOT / 'BPS-INSTALL-RESULT.txt', result.encode())
        print(result)
    finally:
        lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpa-container')
    parser.add_argument('--manager-container')
    parser.add_argument('--plugin-only', action='store_true', help='Explicitly skip the companion Manager panel')
    parser.add_argument('--sync-timezone', action='store_true', help='Only synchronize changed host timezone; no build or restart')
    args = parser.parse_args()
    binary = verify_binary_bundle()
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise RuntimeError('Run on the Ubuntu server as root.')
    ids = run(['docker', 'ps', '-q'], True).decode().split()
    containers = json.loads(run(['docker', 'inspect'] + ids, True)) if ids else []
    cpa = choose(containers, args.cpa_container, 'cli-proxy-api')
    if args.sync_timezone:
        sync_timezone(cpa)
        return
    manager = None
    if not args.plugin_only:
        manager = choose(containers, args.manager_container, 'cpa-manager-plus')
        compose_context(manager)
        if not any(m.get('Destination') == '/data' for m in manager.get('Mounts', [])):
            raise RuntimeError('Manager persistent /data mount is required.')
    install(cpa, binary=binary)
    if manager:
        spec = importlib.util.spec_from_file_location('bps_panel', ROOT / 'panel/scripts/upgrade-bps-panel.py')
        panel = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(panel)
        panel.CONTAINER = manager['Name'].lstrip('/')
        try:
            panel.main()
        except Exception:
            print('BPS plugin is installed, but panel installation failed. Fix the reported cause and rerun install.sh.')
            raise
    print('Installation complete. Refresh Manager with Ctrl+F5. For a new BPS account, finish BPS authorization in the panel.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not print captured configuration, environment variables or keys.
        print('STOP:', str(exc), file=sys.stderr)
        sys.exit(1)
