# Local RunPod launcher

Start one configured pod, check its status, and optionally connect through SSH.
The API connection defaults to a loopback-only SSH tunnel. This helper never
creates or deletes pods and never edits their image, template, volume or keys.

## Requirements

- Python 3.11 or later and OpenSSH on the PC; no pip packages required.
- An existing RunPod API key configured through runpodctl, or RUNPOD_API_KEY in the environment.
- Your existing SSH identity available to OpenSSH, and its public key installed on the pod.

The helper reads the existing key from `~/.runpod/config.toml`; it does not copy it
into this project, print it, or send it to the GPU pod. Control calls go to RunPod.

## Configure once

Copy `runpod-local.example.json` to `runpod-local.json` beside the script. Set
`pod_id` to the pod you want to manage. Keep `local_port` at 18188 unless occupied.
The actual local configuration is gitignored. If you replace or delete a pod,
update this ID. The changing SSH IP and port are discovered automatically.

## Windows menu

Double-click `RunPod.cmd`:

1. **Status** — show pod state, current SSH endpoint, and image.
2. **Start and wait** — resume the configured pod if stopped, then wait for SSH and ComfyUI.
3. **Start + API tunnel** — do the same and keep a loopback tunnel open.
4. **API tunnel only** — connect to a running pod without starting a stopped one.
5. **SSH shell** — open an interactive shell on the running pod.

Keep the tunnel window open while your application uses `http://127.0.0.1:18188`.
Ctrl+C closes the tunnel and leaves the pod running. Starting a stopped pod resumes
its normal GPU billing; an already-running pod receives no additional start request.

Only a new SSH endpoint's first host key is accepted automatically. A changed,
already-known host key is rejected for manual verification. No password or private
key is embedded in the script.

## Command-line use

```powershell
python runpod_local.py status
python runpod_local.py start
python runpod_local.py start --tunnel
python runpod_local.py connect
python runpod_local.py ssh
```

Use `--pod-id` to override the config for one run, `--timeout` to change the 15-minute
startup wait, or `--local-port` to select a different local port. A pod pulling a
large image can take time; a timeout does not stop it or create a replacement.

A diagnostic opens and checks a tunnel, then closes only that temporary tunnel:

```powershell
python runpod_local.py connect --check-only --local-port 18189
```

The helper checks status, discovers the current SSH mapping, verifies the ComfyUI
HTTP response over SSH, and then checks the forwarded local endpoint. It does not
submit a generation automatically. See [the API guide](../../pod-template/API_ACCESS.md)
for the separate generation client and frontend-compiled reference workflow.

## Validation

Five lifecycle tests cover no duplicate start for a running pod, resuming only the
selected stopped pod, refusal to recreate terminated pods, dynamic SSH-port discovery,
and refusal to auto-start from the connect action. A live check against the current
pod passed status discovery, ComfyUI readiness and a temporary tunnel to the local PC.
The same RunPod stop/start control service was also used successfully during deployment testing.
