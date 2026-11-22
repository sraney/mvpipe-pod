# Build and validation summary

Updated November 22, 2026.

## Published compatibility-corrected candidate

- Build: [successful GitHub Actions run](https://github.com/sraney/mvpipe-pod/actions/runs/45077389004).
- Source revision: `7dd1952a8b5f547d7a51c2eb6ec59c3ca6b02d9e`.
- Candidate tag: `ghcr.io/sraney/mvpipe-pod:h3-timeline-compat-candidate`.
- Immutable deployment reference:

```text
ghcr.io/sraney/mvpipe-pod@sha256:e94d648521d1667f9aab1b64a909414c6997118ca05e947ce96bab189ccd1d3a
```

The build passed worker-control and node-restoration tests, dependency consistency,
shell syntax, CPU server startup, and registration of all ten optional node packages.
GitHub's checks do not perform GPU inference.

## What changed

OBVPM's compatibility gate identifies loaded packages whose immediate parent is
named `custom_nodes`. The original persistent profile path ended in `timeline`,
so the gate incorrectly reported installed packages as missing.

Startup now creates a conventional load-path alias:

```text
/workspace/comfyui-config/load-paths/timeline/custom_nodes
    -> /workspace/comfyui-config/active-nodes/timeline
```

This changes discovery without moving node sources, duplicating models, bypassing
the compatibility gate, or changing dependency pins. The regression test checks that
this alias resolves to cached sources and that disabled-node state is preserved.

## Software and storage

| Component | Version or location |
| --- | --- |
| ComfyUI | 0.46.0 |
| Python | 3.12 |
| PyTorch | 2.11.0+cu130 |
| CUDA runtime | 13.0; CUDA base image 13.0.2 |
| ComfyUI-Manager | 4.2.2, native integration |
| Models | /workspace/models |
| Workflows and settings | /workspace/user |
| Optional node repositories | /workspace/custom_nodes |
| Default profile | timeline, ten packages plus three image-owned H3 helpers |

A compatible NVIDIA driver is required. A host supporting CUDA 13.2 can run this
CUDA 13.0 image. Validation used one RTX PRO 6000 Blackwell with 96 GB VRAM.
48 GB is a planning recommendation, not a measured minimum for this workflow.

## Completed GPU integration checks

These results distinguish the original candidate, its temporary live mapping fix,
and the corrected image deployed from its published digest. The corrected image
now passes reference generation and full pod stop/start recovery checks.

| Check | Result |
| --- | --- |
| Original expanded image, cat-and-yarn render | Passed: 640 x 384, 124 frames, 24 fps, about 5.17 seconds |
| Root take with tiny-VAE live preview | Passed; context and conditioning sidecars saved |
| Masked continuation from saved latent context | Passed; 39-frame context window |
| Timeline preview and export | Passed: 209 frames, about 8.71 seconds, video and audio |
| ComfyUI server restart and fresh generation | Passed; node packages loaded again |
| Dependency-restoration recheck | Passed; no broken Python requirements |
| Large supplied reference workflow, generation path | Passed after applying the corrected mapping live; compatibility gate enabled, reference image supplied, preview bypassed |
| Full pod stop/start, persistent models and workflows | Preserved |
| Temporary application-file patch after full pod stop/start | Lost; this triggered the corrected image build |
| Corrected digest, fresh deployment and GPU rerun | Passed: full reference generation path, 124 frames, about 5.17 seconds; 212.79 seconds including cold model loading |
| Corrected digest, full pod stop/start | Passed: startup script, workflow and checked model fingerprints preserved; corrected load path restored; all ten node packs registered; compatibility gate rerun passed. GPU sampling was not repeated after this final stop/start. |

The large reference workflow's successful generation test does not cover every
optional branch, upscale/refine configuration, Turbo preset, or custom-node feature.

## Preview timing

A matching root-generation comparison took about **85.10 seconds with live preview**
and **25.43 seconds without it**, about 70% less total time in that comparison.
This is a measured example, not a general speed guarantee. A cold render after
restarting ComfyUI took about 151 seconds including model loading.

Bypass `H3LivePreview`, or connect its model input directly to its downstream model
consumers, to remove per-step preview decoding. Final video decoding and saving remain.
The `latent RGB (no tiny VAE)` option is a lighter preview, not a complete off switch.

## Saved workflows and model transfers

The workflow library contains `H3 OBVPM Timeline - Prepared` and this folder:

```text
H3 Validation/
  01 - Cat Root - Live Preview.json
  02 - Cat Root - Preview Off.json
  03 - Cat Continuation and Timeline.json
  04 - Full Reference Workflow Test.json
```

The first three UI graphs were generated from tested API graphs. The fourth is a
copy of the supplied reference workflow with a test image and bounded settings.
All four missing timeline model files, about 5.08 GB total, were downloaded on the
PC and checksum-verified again after upload to the shared model library. All twelve
model selections in the prepared workflow were found in ComfyUI's model dropdowns.

## API use

The visual workflow contains frontend subgraphs and virtual connections. A generic
UI-to-API conversion lost connections, so its stripped output was not used.
ComfyUI's own frontend successfully compiled and ran a 62-node API graph; that exact
graph is saved under `/workspace/comfy-setup/validation/reference-workflow-compiled-api.json`.
It can be submitted to ComfyUI's `/prompt` endpoint and polled through `/history`.

A local client was prepared. An initial request through the public RunPod proxy
returned HTTP 403; external API connectivity is not yet validated. An SSH tunnel is
an alternative to investigate. This connectivity issue is separate from the node
compatibility gate and the successful on-server API tests.

## Deploy without changing template identity

1. Keep the legacy/fallback template unchanged.
2. Edit the new template's container image to the immutable reference above; keep its ID.
3. Update the existing pod's own image, or deploy that template with the existing network volume.
4. Keep the volume mounted at `/workspace`; do not replace it with an empty volume.
5. Leave the startup command empty. Use the established SSH public key and ports.
6. Confirm the corrected load path, then run the saved reference test.
7. Stop/start the pod and repeat the check before marking restart validation complete.

Keep the previous image digest for rollback. No models or credentials are included
in this repository or image. Do not publish SSH private keys or service API keys.
