"""Submit the validated H3 reference graph to ComfyUI from any Python application."""
import argparse
import copy
import json
from pathlib import Path
import time
import urllib.request


def request(server, endpoint, data=None):
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(server.rstrip('/') + endpoint, data=payload,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def run(server, graph, prompt=None, seed=None, timeout=1800):
    graph = copy.deepcopy(graph)
    if prompt is not None:
        graph['761:763']['inputs']['value'] = prompt
    if seed is not None:
        graph['765']['inputs']['seed'] = seed
    submitted = request(server, '/prompt', {'prompt': graph})
    prompt_id = submitted['prompt_id']
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = request(server, '/history/' + prompt_id).get(prompt_id)
        if result:
            if result.get('status', {}).get('status_str') != 'success':
                raise RuntimeError(json.dumps(result.get('status', {})))
            return result
        time.sleep(2)
    raise TimeoutError('Render still running; prompt ID: ' + prompt_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', default='http://127.0.0.1:18188', help='ComfyUI base URL; defaults to the local SSH tunnel')
    parser.add_argument('--workflow', type=Path, default=Path(__file__).with_name('reference-workflow-api.json'))
    parser.add_argument('--prompt')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    result = run(args.server, json.loads(args.workflow.read_text()), args.prompt, args.seed, args.timeout)
    print(json.dumps(result, indent=2))
