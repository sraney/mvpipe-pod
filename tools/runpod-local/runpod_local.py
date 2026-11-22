"""Start one configured RunPod and connect over SSH; Python 3.11+, no pip packages."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request

DEFAULT_CONFIG = Path(__file__).with_name('runpod-local.json')


class RunPod:
    def __init__(self, key=None):
        self.key = key or os.environ.get('RUNPOD_API_KEY')
        config = Path.home() / '.runpod/config.toml'
        if not self.key and config.exists():
            self.key = tomllib.loads(config.read_text()).get('apikey')
        if not self.key:
            raise RuntimeError('RunPod authentication missing. Configure runpodctl or RUNPOD_API_KEY.')

    def query(self, query, variables):
        request = urllib.request.Request(
            'https://api.runpod.io/graphql',
            data=json.dumps({'query': query, 'variables': variables}).encode(),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError('RunPod control service returned HTTP ' + str(error.code)) from None
        except urllib.error.URLError:
            raise RuntimeError('Cannot reach the RunPod control service.') from None
        if result.get('errors'):
            message = '; '.join(str(x.get('message', 'Control request failed')) for x in result['errors'])
            raise RuntimeError(message.replace(self.key, '[redacted]'))
        return result['data']

    def status(self, pod_id):
        query = '''query($id:String!) { pod(input:{podId:$id}) {
            id name desiredStatus imageName runtime { uptimeInSeconds ports {
                ip isIpPublic privatePort publicPort type
            } }
        } }'''
        pod = self.query(query, {'id': pod_id}).get('pod')
        if not pod:
            raise RuntimeError('Configured pod was not found. Update runpod-local.json if it was replaced.')
        return pod

    def start(self, pod_id):
        pod = self.status(pod_id)
        if pod['desiredStatus'] == 'RUNNING':
            print('Pod is already running; no start request sent.', flush=True)
            return
        if pod['desiredStatus'] != 'EXITED':
            raise RuntimeError('Cannot start a pod in state ' + pod['desiredStatus'])
        query = '''mutation($id:String!) { podResume(input:{podId:$id,gpuCount:1}) {
            id desiredStatus
        } }'''
        self.query(query, {'id': pod_id})
        print('Start accepted. GPU billing resumes at the pod rate.', flush=True)


def endpoint(pod):
    for port in (pod.get('runtime') or {}).get('ports', []):
        if port.get('privatePort') == 22 and port.get('isIpPublic') and port.get('type') == 'tcp':
            return str(port['ip']), int(port['publicPort'])
    return None


def ssh_command(address, batch=True):
    command = [shutil.which('ssh') or 'ssh', '-o', 'StrictHostKeyChecking=accept-new',
               '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=30',
               '-o', 'ServerAliveCountMax=3']
    if batch:
        command += ['-o', 'BatchMode=yes']
    return command + ['-p', str(address[1]), 'root@' + address[0]]


def wait_ready(api, pod_id, timeout):
    deadline = time.monotonic() + timeout
    last_state = None
    while time.monotonic() < deadline:
        pod = api.status(pod_id)
        state = (pod['desiredStatus'], endpoint(pod))
        if state != last_state:
            print('Pod state:', state[0], '| SSH:', state[1] or 'not assigned yet', flush=True)
            last_state = state
        address = endpoint(pod)
        if address and pod['desiredStatus'] == 'RUNNING':
            check = subprocess.run(ssh_command(address) + [
                'curl --max-time 8 -fsS http://127.0.0.1:8188/system_stats'],
                capture_output=True, text=True, timeout=25)
            if check.returncode == 0:
                try:
                    version = json.loads(check.stdout)['system']['comfyui_version']
                    print('ComfyUI ready:', version, flush=True)
                    return address
                except (ValueError, KeyError):
                    pass
            elif 'REMOTE HOST IDENTIFICATION HAS CHANGED' in check.stderr:
                raise RuntimeError('SSH host key changed. Verify it manually; it was not bypassed.')
            elif 'Permission denied' in check.stderr:
                raise RuntimeError('SSH authentication failed. Check the pod public key and your SSH agent.')
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise TimeoutError('Pod is not ready yet. It may still be pulling the image. Check status and retry.')


def tunnel(address, local_port, check_only=False):
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', local_port)) == 0:
            raise RuntimeError('Local port is already in use; use --local-port with another port.')
    command = ssh_command(address)
    command[1:1] = ['-N', '-o', 'ExitOnForwardFailure=yes', '-L',
                    f'127.0.0.1:{local_port}:127.0.0.1:8188']
    process = subprocess.Popen(command)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('SSH tunnel exited before it became ready.')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{local_port}/system_stats', timeout=3) as response:
                    data = json.load(response)
                print('Tunnel ready:', f'http://127.0.0.1:{local_port}',
                      '| ComfyUI', data['system']['comfyui_version'], flush=True)
                break
            except (OSError, ValueError, KeyError):
                time.sleep(1)
        else:
            raise TimeoutError('Tunnel did not answer before the timeout.')
        if not check_only:
            print('Keep this window open. Ctrl+C closes the tunnel; it does not stop the pod.', flush=True)
            process.wait()
            if process.returncode:
                raise RuntimeError('Tunnel disconnected. Reconnect to discover the current SSH endpoint.')
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def execute(args):
    config = json.loads(args.config.read_text()) if args.config.exists() else {}
    pod_id = args.pod_id or config.get('pod_id')
    if not pod_id or not re.fullmatch(r'[a-z0-9]{8,40}', pod_id):
        raise RuntimeError('Set pod_id in runpod-local.json or pass --pod-id.')
    api = RunPod()
    if args.action == 'status':
        pod = api.status(pod_id)
        print(json.dumps({'name': pod['name'], 'state': pod['desiredStatus'],
                          'ssh': endpoint(pod), 'image': pod['imageName']}, indent=2))
        return
    if args.action == 'start':
        api.start(pod_id)
    elif api.status(pod_id)['desiredStatus'] != 'RUNNING':
        raise RuntimeError('Pod is stopped. Use the start command to resume it explicitly.')
    address = wait_ready(api, pod_id, args.timeout)
    if args.action == 'ssh':
        subprocess.run(ssh_command(address, batch=False), check=True)
    elif args.action == 'connect' or args.tunnel:
        tunnel(address, args.local_port or config.get('local_port', 18188), args.check_only)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=['menu', 'status', 'start', 'connect', 'ssh'], default='menu')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--pod-id')
    parser.add_argument('--local-port', type=int, choices=range(1024, 65536), metavar='PORT')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--tunnel', action='store_true', help='After start, keep an API tunnel open')
    parser.add_argument('--check-only', action='store_true', help='Verify the tunnel then close it')
    args = parser.parse_args()
    if args.action != 'menu':
        execute(args)
        return
    while True:
        print('\n1 Status  2 Start and wait  3 Start + API tunnel  4 API tunnel only  5 SSH shell  0 Exit')
        choice = input('Choose: ').strip()
        if choice == '0':
            return
        options = {'1': ('status', False), '2': ('start', False), '3': ('start', True),
                   '4': ('connect', False), '5': ('ssh', False)}
        if choice not in options:
            continue
        args.action, args.tunnel = options[choice]
        try:
            execute(args)
        except KeyboardInterrupt:
            print('\nConnection closed; pod left running.')
        except Exception as error:
            print('Error:', error)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nConnection closed; pod left running.')
    except Exception as error:
        print('Error:', error, file=sys.stderr)
        sys.exit(1)
