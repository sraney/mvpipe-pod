"""Exercise the real worker controls against a small stand-in HTTP process."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
FAKE_APP = '''import http.server,json,pathlib,sys
port=int(sys.argv[sys.argv.index('--port')+1])
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/queue':
   body={'queue_running':[1] if pathlib.Path(__file__).with_name('busy').exists() else [],'queue_pending':[]}
  else: body={'system':{'argv':[__file__],'comfyui_version':'test'}}
  self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(body).encode())
 def log_message(self,*args): pass
http.server.HTTPServer(('127.0.0.1',port),Handler).serve_forever()
'''


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux process control')
class WorkerLifecycleTest(unittest.TestCase):
    def test_controls_and_shutdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, state = root / 'code', root / 'state'
            code.mkdir()
            (code / 'main.py').write_text(FAKE_APP)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, WORKSPACE=str(root / 'workspace'), COMFYUI_DIR=str(code),
                       COMFYUI_CONTROL_ROOT=str(state), COMFYUI_PORT=str(port))
            with (root / 'supervisor.log').open('w') as log:
                supervisor = subprocess.Popen([sys.executable, str(SCRIPTS / 'supervise.py')],
                                              env=env, stdout=log, stderr=subprocess.STDOUT)
                child_pid = None
                try:
                    deadline = time.monotonic() + 5
                    while not (state / 'supervisor.pid').exists() and time.monotonic() < deadline:
                        time.sleep(.1)

                    def control(action):
                        return subprocess.run([sys.executable, str(SCRIPTS / 'control.py'), action],
                                              env=env, capture_output=True, text=True, timeout=10)

                    result = control('start')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    first_pid = int((state / 'comfyui.pid').read_text())
                    (code / 'busy').touch()
                    self.assertNotEqual(control('stop').returncode, 0)
                    self.assertFalse((state / 'stopped').exists())
                    self.assertTrue(Path(f'/proc/{first_pid}').exists())
                    (code / 'busy').unlink()
                    result = control('stop')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    time.sleep(3.5)
                    self.assertFalse((state / 'comfyui.pid').exists(), 'Stopped worker respawned')
                    result = control('start')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    second_pid = int((state / 'comfyui.pid').read_text())
                    self.assertNotEqual(first_pid, second_pid)
                    result = control('restart')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    child_pid = int((state / 'comfyui.pid').read_text())
                    self.assertNotEqual(second_pid, child_pid)
                    self.assertIn('Version: test', control('status').stdout)
                finally:
                    supervisor.terminate()
                    supervisor.wait(timeout=35)
                self.assertFalse(Path(f'/proc/{child_pid}').exists(), 'Worker survived supervisor shutdown')


if __name__ == '__main__':
    unittest.main()
