# mvpipe pod template

A Docker image that turns a rented RunPod GPU into an mvpipe generation host: ComfyUI at a pinned
release with the MiniMax H3 nodes (including *Add Guide*, which v0.30.0 lacks), the latent upscaler,
KJNodes, VideoHelperSuite, ffmpeg 7+, one ComfyUI worker per GPU, and a boot script that reports
what is missing instead of failing silently.

What lives where:

| Place | Holds | Survives a pod restart? |
| --- | --- | --- |
| The image (`/opt`) | Python, torch, ComfyUI, custom nodes, ffmpeg, scripts | Rebuilt from the image every start |
| Network volume (`/workspace`) | `models/`, `input/`, `output/`, `user/`, `logs/`, `mvpipe/` | Yes, and it bills while it exists |

Pinned versions (all in the `Dockerfile` and `config/custom_nodes.txt`): ComfyUI v0.37.0, torch 2.11.0
for CUDA 12.8 (works on Blackwell and on any host driver 570+), Python 3.12 (Ubuntu 24.04).

## 1. Accounts you need

- **RunPod** with credit added.
- **A place to host the image**, either Docker Hub or GitHub (free). RunPod pulls the image from there.
- Optional: a **Hugging Face token** (only if a model download asks for a login).

## 2. Build and publish the image (once, and again whenever you change a pin)

### Option A: on your own PC (needs Docker; about 10 GB of disk, 20+ minutes)

```bash
cd pod-template
docker build -t YOURNAME/mvpipe-pod:latest .
docker login
docker push YOURNAME/mvpipe-pod:latest
```

On Windows, install Docker Desktop first and run these in PowerShell. Replace `YOURNAME` with your
Docker Hub user name. The push is large (several GB), so use a wired connection.

### Option B: let GitHub build it (no Docker on your PC)

1. Create a GitHub repo and upload the `pod-template/` folder.
2. Copy `github-actions-build.yml` to `.github/workflows/build-pod-image.yml` in that repo.
3. Actions tab, *build-pod-image*, **Run workflow**. The image appears as `ghcr.io/YOURNAME/mvpipe-pod:latest`.
4. Package settings: set the package to **Public** so RunPod can pull it without a login.

## 3. Create the network volume

RunPod console, *Storage*, *New Network Volume*.

- **Datacenter**: choose one that offers your GPU (RTX PRO 6000 or similar, 96 GB). The volume
  can only attach to pods in the same datacenter, so check GPU availability first.
- **Size**: 100 GB minimum (the H3 set is about 45 GB, plus outputs and LoRAs). 150 GB leaves room.

## 4. Create the pod template

RunPod console, *Templates*, *New Template*. Field names can differ slightly from this list.

| Field | Value |
| --- | --- |
| Name | `mvpipe-comfyui` |
| Container image | `YOURNAME/mvpipe-pod:latest` (or the `ghcr.io/...` name) |
| Container disk | 60 GB |
| Volume disk | 0 (you attach the network volume when deploying) |
| Volume mount path | `/workspace` |
| Expose HTTP ports | `8188, 8189, 8190, 8191, 8888` (8189+ are the extra GPUs' workers) |
| Expose TCP ports | `22` |
| Container start command | leave empty (the image starts `/start.sh`) |

Environment variables:

| Name | Value | Notes |
| --- | --- | --- |
| `PUBLIC_KEY` | your SSH public key | Optional. Without it sshd is not started. Create one with `ssh-keygen -t ed25519`, then paste the contents of `~/.ssh/id_ed25519.pub`. |
| `ENABLE_JUPYTER` | `1` | Optional. Lets you browse and upload files in a browser. |
| `JUPYTER_TOKEN` | a long random string | Used only when `ENABLE_JUPYTER=1`. If you leave it out, one is generated and saved to `/workspace/logs/jupyter_token.txt`. |
| `HF_TOKEN` | your Hugging Face token | Optional. Only for model downloads that need a login. |
| `COMFYUI_EXTRA_ARGS` | e.g. `--fast` | Optional extra ComfyUI flags. |

## 5. First start

1. *Pods*, **Deploy**, pick the GPU, tick **Network Volume** and choose yours, pick `mvpipe-comfyui`.
2. Open the pod's **Logs**. You should see `[mvpipe-boot]` lines: sshd (or "not started"), a
   `[models]` report, then `worker 0 starting on port 8188`.
3. The first boot has no models yet, so the report lists them as MISSING. That is expected.

## 6. Put the models on the volume

Open a terminal on the pod (the console's *Connect* tab, or Jupyter's terminal) and run:

```bash
python3 /opt/mvpipe/scripts/verify_models.py --download
```

It downloads the confirmed files (about 44 GB) into `/workspace/models/...`, resumes if interrupted,
and prints the report again. Tip: download on a cheap pod instead of the GPU pod to save money. Any
pod attached to the same volume works, since the script needs only Python.

Two files are marked *source not confirmed*, so they are skipped by default:

- the **latent upscaler**: the spec's file name was not found online; the published file is
  `minimax_h3_latent_upscaler_3d_conv_v1_fp16.safetensors` (probably the same model);
- the **lightx2v LoRA**: no file with the spec's name was found; the closest is the 1.38 GB
  `minimax_h3_fl2v_turbo_4step_v0.1.safetensors`.

If you have the originals on your current pod, copy them to `/workspace/models/latent_upscale_models/`
and `/workspace/models/loras/`. Otherwise add `--unconfirmed` to fetch the closest matches and test them.

Then restart the pod's workers (or stop and start the pod) so ComfyUI sees the new files.

## 7. Check it works

```bash
python3 /opt/mvpipe/scripts/check_nodes.py --wait 300
```

Every line should say `OK`. A `MISSING` on `MiniMaxH3AddGuide` means the ComfyUI version is too old.
The pod's address for mvpipe is `https://<POD_ID>-8188.proxy.runpod.net` (the pod ID is on the pod's
page); the second GPU is the same address with `-8189`.

## 8. Day to day

- **Stop the pod** when you are not generating. You pay for the GPU while it runs, and for the
  volume while it exists. Stopping the pod keeps the volume.
- The first job after a restart is slow (7-15 minutes of model loading). That is normal.
- Logs: `/workspace/logs/comfyui-gpu0.log` (and `-gpu1`, ...), `model_check.json`, `pod_agent.log`.
- To update a pin: edit `Dockerfile` or `config/custom_nodes.txt`, rebuild, push, redeploy.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Pod starts but `8188` link gives a 502 | ComfyUI is still starting; read `comfyui-gpu0.log`. Wait a few minutes. |
| Only one ComfyUI port works on a 2-GPU pod | Ports `8189+` are missing from the template's HTTP port list. |
| `CUDA error: no kernel image` | Image built for the wrong CUDA; keep `cu128` (or newer) torch for Blackwell. |
| Worker restarts every 5 s | Read the end of its log; usually a bad custom node or a missing model. |
| Out-of-memory loading the model | The GPU is below 96 GB; this is the open VRAM question in the spec. |

## Not verified yet

- A real generation on a GPU. The image has been built and ComfyUI checked for the H3 nodes, but no take has been rendered with it.
- The exact RunPod console field names, which change over time.
- Whether the two "source not confirmed" files are the ones your workflow expects.
