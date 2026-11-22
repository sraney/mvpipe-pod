#!/usr/bin/env python3
"""Own one ComfyUI process and its runtime control state."""
import fcntl
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

STATE = Path(os.environ.get('COMFYUI_CONTROL_ROOT', '/run/mvpipe'))
WORKSPACE = Path(os.environ.get('WORKSPACE', '/workspace'))
CODE = Path(os.environ.get('COMFYUI_DIR', '/opt/ComfyUI'))


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    lock = (STATE / 'supervisor.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('The ComfyUI supervisor is already running.')
    (STATE / 'supervisor.pid').write_text(str(os.getpid()))
    (WORKSPACE / 'logs').mkdir(parents=True, exist_ok=True)
    user = Path(os.environ.get('COMFYUI_USER_DIRECTORY', str(WORKSPACE / 'user')))
    output = Path(os.environ.get('COMFYUI_OUTPUT_DIRECTORY', str(WORKSPACE / 'output')))
    for directory in [user, output, WORKSPACE / 'input']:
        directory.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(CODE / 'main.py'), '--listen', os.environ.get('COMFYUI_LISTEN', '0.0.0.0'),
               '--port', os.environ.get('COMFYUI_PORT', '8188'), '--extra-model-paths-config',
               os.environ.get('COMFYUI_EXTRA_MODEL_PATHS_CONFIG', '/opt/mvpipe/extra_model_paths.yaml'), '--input-directory', str(WORKSPACE / 'input'),
               '--output-directory', str(output), '--user-directory', str(user),
               '--temp-directory', '/tmp/comfyui', '--disable-auto-launch']
    command += shlex.split(os.environ.get('COMFYUI_EXTRA_ARGS', ''))
    if os.environ.get('ENABLE_MANAGER', '1') == '1':
        command.append('--enable-manager')
    child = None
    stopping = False

    def shutdown(signum, frame):
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        while not stopping:
            if (STATE / 'stopped').exists():
                time.sleep(.5)
                continue
            with (WORKSPACE / 'logs/comfyui-gpu0.log').open('ab') as stream:
                child = subprocess.Popen(command, cwd=CODE, stdin=subprocess.DEVNULL,
                                         stdout=stream, stderr=subprocess.STDOUT)
                (STATE / 'comfyui.pid').write_text(str(child.pid))
                print(f'[mvpipe] ComfyUI started (PID {child.pid}).', flush=True)
                while child.poll() is None and not stopping:
                    time.sleep(.5)
                if stopping and child.poll() is None:
                    try:
                        child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                print(f'[mvpipe] ComfyUI exited ({child.returncode}).', flush=True)
                child = None
                (STATE / 'comfyui.pid').unlink(missing_ok=True)
            if not stopping:
                time.sleep(3)
    finally:
        (STATE / 'comfyui.pid').unlink(missing_ok=True)
        (STATE / 'supervisor.pid').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
