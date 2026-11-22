#!/usr/bin/env python3
"""Start, stop, or inspect the single worker managed by this image."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import time
import urllib.error
import urllib.request

STATE = Path(os.environ.get('COMFYUI_CONTROL_ROOT', '/run/mvpipe'))
CODE = Path(os.environ.get('COMFYUI_DIR', '/opt/ComfyUI'))
PORT = int(os.environ.get('COMFYUI_PORT', '8188'))


def api(path):
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/{path}', timeout=3) as response:
        return json.load(response)


def owned_pid(filename, expected):
    try:
        pid = int((STATE / filename).read_text())
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        return pid if str(expected).encode() in args else None
    except (FileNotFoundError, ProcessLookupError, ValueError):
        return None


def worker():
    return owned_pid('comfyui.pid', CODE / 'main.py')


def stop():
    pid = worker()
    if pid:
        queue = api('queue')
        if queue['queue_running'] or queue['queue_pending']:
            raise SystemExit('ComfyUI has active or queued work; wait before stopping.')
    (STATE / 'stopped').touch()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 35
    while worker() and time.monotonic() < deadline:
        time.sleep(.5)
    if worker():
        raise SystemExit('ComfyUI did not stop gracefully; inspect its log.')
    print('ComfyUI stopped.')


def start():
    if not owned_pid('supervisor.pid', Path(__file__).with_name('supervise.py')):
        raise SystemExit('The image supervisor is not running; restart the container.')
    (STATE / 'stopped').unlink(missing_ok=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            stats = api('system_stats')
            if worker() and stats['system']['argv'][0] == str(CODE / 'main.py'):
                print('ComfyUI ready:', stats['system']['comfyui_version'])
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise SystemExit('Readiness timed out; inspect /workspace/logs/comfyui-gpu0.log.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status'])
    action = parser.parse_args().action
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action in ['stop', 'restart']:
            stop()
        if action in ['start', 'restart']:
            start()
        if action == 'status':
            print('Managed worker PID:', worker())
            try:
                stats, queue = api('system_stats'), api('queue')
                print('Application:', stats['system']['argv'][0])
                print('Version:', stats['system']['comfyui_version'])
                print('Running:', len(queue['queue_running']), 'Queued:', len(queue['queue_pending']))
            except (OSError, ValueError):
                print('API unavailable.')


if __name__ == '__main__':
    main()
