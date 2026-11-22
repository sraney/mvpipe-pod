# Local applications through an SSH tunnel

Use SSH tunneling as the default API connection. Bind the tunnel to loopback so
other machines cannot use the forwarded port. ComfyUI remains behind the existing
SSH authentication; no security protections need to be disabled.

## 1. Open the tunnel

Copy the current SSH host and port from RunPod. Replace `SSH_HOST` and `SSH_PORT`:

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:18188:127.0.0.1:8188 -p SSH_PORT root@SSH_HOST
```

Keep that terminal open while the application uses ComfyUI. The local API base URL is:

```text
http://127.0.0.1:18188
```

RunPod may assign a different SSH port after a pod stop/start. Close the old tunnel
and reconnect using the new port. Do not change the application's local base URL.
The tunnel can also carry the normal ComfyUI browser interface.

## 2. Check connectivity

```powershell
Invoke-RestMethod http://127.0.0.1:18188/system_stats
Invoke-RestMethod http://127.0.0.1:18188/queue
```

## 3. Run the reference workflow from Python

Download `validation/run_h3_reference.py` and `validation/reference-workflow-api.json`
to the same folder. The client uses only Python's standard library.

```powershell
python run_h3_reference.py --seed 20261129
```

Optional overrides:

```powershell
python run_h3_reference.py --seed 20261130 --prompt "The orange cat from <Picture 1> gently taps the blue yarn ball. Natural movement and quiet room ambience."
```

The graph uses the existing shared models and the reference image at
`/workspace/input/validation/cat_reference.png`. The validation setup created that
image from an earlier cat take; a separate empty volume will not have it.
The API export is the 62-node graph compiled by ComfyUI's frontend, not the raw
visual workflow. It preserves the resolved subgraphs and virtual connections.

## 4. Integrate with another local application

The client exposes `run(server, graph, prompt=None, seed=None, timeout=1800)`:

```python
import json
from pathlib import Path
from run_h3_reference import run

graph = json.loads(Path("reference-workflow-api.json").read_text())
result = run("http://127.0.0.1:18188", graph, seed=20261131)
print(result["outputs"])
```

Submission is `POST /prompt` with `{"prompt": graph}`. The response contains
`prompt_id`; poll `GET /history/{prompt_id}` until it completes. Inspect
`status.status_str` for success and preserve errors rather than treating an
accepted queue entry as a completed render.

The reference workflow's result is under `outputs["1218"]["h3_result"]`; its `clip`
field is relative to the server's output directory. Retrieve the video with
`GET /view?filename=FILE.mp4&subfolder=FOLDER&type=output` through the same tunnel.
For an input image supplied by your app, use `POST /upload/image` and update the
LoadImagesCompose node's `layers` JSON to the returned input filename.

## Validation scope

Public-proxy GET status requests succeeded, but POST workflow submission returned
HTTP 403. The SSH tunnel passed the complete PC-to-pod test: workflow submission, history
polling to successful generation, and video retrieval through `/view` (HTTP 200,
625,456 bytes for the validation clip). This approach
does not depend on browser cookies or changes to ComfyUI's origin policy.
