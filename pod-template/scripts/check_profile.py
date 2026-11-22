#!/usr/bin/env python3
"""Fail image verification if any selected node pack failed to register nodes."""
import argparse
import json
import os
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8188')
    args = parser.parse_args()
    profile = os.environ.get('CUSTOM_NODE_PROFILE', 'timeline')
    workspace = Path(os.environ.get('WORKSPACE', '/workspace'))
    manifest = workspace / 'comfyui-config/profiles' / (profile + '.json')
    nodes = json.loads(manifest.read_text())['nodes']
    with urllib.request.urlopen(args.url + '/object_info', timeout=30) as response:
        info = json.load(response)
    missing = []
    for node in nodes:
        if not node.get('enabled', True):
            continue
        module = 'custom_nodes.' + node['name']
        count = sum(value.get('python_module') == module for value in info.values())
        print(node['name'] + ': ' + str(count) + ' nodes registered')
        if not count:
            missing.append(node['name'])
    if missing:
        raise SystemExit('Node packs did not load: ' + ', '.join(missing))


if __name__ == '__main__':
    main()
