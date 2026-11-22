#!/usr/bin/env python3
"""Restore a persistent, versioned custom-node profile before ComfyUI starts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tomllib


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def restore(workspace, package, profile, snapshot=False):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', profile):
        raise ValueError('Invalid custom-node profile name')
    settings = workspace / 'comfyui-config'
    manifest = settings / 'profiles' / (profile + '.json')
    active = settings / 'active-nodes' / profile
    library = workspace / 'custom_nodes'
    for directory in [manifest.parent, active, library, workspace / 'logs']:
        directory.mkdir(parents=True, exist_ok=True)
    if not manifest.exists():
        shutil.copy2(package / 'node-profiles' / (profile + '.json'), manifest)
    nodes = json.loads(manifest.read_text())['nodes']
    policy = {}
    if not snapshot:
        for node in nodes:
            name, url, commit = node['name'], node['url'], node['commit']
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]+', name):
                raise ValueError('Invalid node directory name: ' + name)
            if not re.fullmatch(r'https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', url):
                raise ValueError('Expected a GitHub repository URL for ' + name)
            if not re.fullmatch(r'[a-f0-9]{40}', commit):
                raise ValueError('Expected an immutable commit for ' + name)
            policy[name] = node.get('install_requirements', True)
            link = active / name
            if not node.get('enabled', True):
                if link.is_symlink():
                    link.unlink()
                continue
            # Preserve Manager's disabled state and any user-installed package.
            if (active / (name + '.disabled')).exists() or (active / '.disabled' / name).exists():
                continue
            if not link.exists():
                target = library / name
                if not target.exists():
                    staging = library / ('.' + name + '.installing-' + str(os.getpid()))
                    run('git', 'init', '-q', str(staging))
                    run('git', '-C', str(staging), 'remote', 'add', 'origin', url)
                    run('git', '-C', str(staging), 'fetch', '-q', '--depth', '1', 'origin', commit)
                    run('git', '-C', str(staging), 'checkout', '-q', 'FETCH_HEAD')
                    if run('git', '-C', str(staging), 'rev-parse', 'HEAD') != commit:
                        raise RuntimeError('Unexpected revision for ' + name)
                    staging.rename(target)
                link.symlink_to(target, target_is_directory=True)

    requirements, direct, revisions, installer_notes = [], [], {}, []
    for node in sorted(active.iterdir()):
        if not node.is_dir() or node.name.startswith('.') or node.name.endswith('.disabled'):
            continue
        if (node / '.git').exists():
            revisions[node.name] = run('git', '-C', str(node), 'rev-parse', 'HEAD')
        if (node / 'install.py').exists():
            installer_notes.append(node.name)
        if not policy.get(node.name, True):
            continue
        if (node / 'requirements.txt').exists():
            requirements.append(node / 'requirements.txt')
        elif (node / 'pyproject.toml').exists():
            project = tomllib.loads((node / 'pyproject.toml').read_text())
            direct.extend(project.get('project', {}).get('dependencies', []))
    frozen = run(sys.executable, '-m', 'pip', 'freeze')
    if snapshot:
        destination = settings / 'snapshots' / time.strftime('%Y%m%d-%H%M%S')
        destination.mkdir(parents=True)
        (destination / 'nodes.json').write_text(json.dumps(revisions, indent=2))
        (destination / 'requirements.lock').write_text(frozen + '\n')
        shutil.copy2(manifest, destination / 'profile.json')
        print('Custom-node snapshot saved:', destination, flush=True)
        return

    content = frozen + json.dumps(direct) + ''.join(p.read_text() for p in requirements)
    content += (package / 'requirements.lock').read_text()
    content += (package / 'optional-requirements.lock').read_text()
    signature = hashlib.sha256(content.encode()).hexdigest()
    marker = settings / ('dependency-state-' + profile + '.json')
    previous = json.loads(marker.read_text()) if marker.exists() else {}
    if previous.get('signature') != signature:
        command = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                   '-c', str(package / 'requirements.lock'), '-c', str(package / 'optional-requirements.lock')]
        for path in requirements:
            command.extend(['-r', str(path)])
        if requirements or direct:
            subprocess.run(command + direct, check=True)
        subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
        frozen = run(sys.executable, '-m', 'pip', 'freeze')
        content = frozen + json.dumps(direct) + ''.join(p.read_text() for p in requirements)
        content += (package / 'requirements.lock').read_text() + (package / 'optional-requirements.lock').read_text()
        marker.write_text(json.dumps({'signature': hashlib.sha256(content.encode()).hexdigest()}))
    runtime = Path(os.environ.get('COMFYUI_CONTROL_ROOT', '/run/mvpipe'))
    runtime.mkdir(parents=True, exist_ok=True)
    config = (package / 'extra_model_paths.yaml').read_text()
    config += '\npersistent_nodes:\n  is_default: true\n  custom_nodes: ' + json.dumps(str(active)) + '\n'
    (runtime / 'extra_model_paths.yaml').write_text(config)
    report = {'profile': profile, 'node_revisions': revisions, 'install_scripts_requiring_review': installer_notes}
    (workspace / 'logs/custom-node-restore.json').write_text(json.dumps(report, indent=2))
    if installer_notes:
        print('Node-specific install.py scripts need separate review:', ', '.join(installer_notes), flush=True)
    print('Persistent node profile ready:', profile, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', action='store_true')
    args = parser.parse_args()
    restore(Path(os.environ.get('WORKSPACE', '/workspace')),
            Path(os.environ.get('MVPIPE_PACKAGE_DIR', '/opt/mvpipe')),
            os.environ.get('CUSTOM_NODE_PROFILE', 'timeline'), args.snapshot)


if __name__ == '__main__':
    main()
