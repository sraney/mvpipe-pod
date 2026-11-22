# H3 acceptance test

`cat-yarn-workflow.json` is the UI workflow. `cat-yarn-api.json` is its API graph.
They use existing model files under `/workspace/models`; nothing is downloaded.

The graph passed on the current pod with ComfyUI 0.46.0 and PyTorch 2.11.0+cu130.
The user approved its 640 x 384, 124-frame, 24 fps video. It ran in about 171 seconds
including cold model loading. This validates the software baseline, not the new image.

To validate a newly built image, open ComfyUI, load `cat-yarn-workflow.json`, and Run.
Expected output: `validation/H3_Cat_Yarn_*.mp4`. Confirm the cat plays with a yarn ball,
the video plays correctly, and no execution error appears. Restart the pod and repeat.

Models used:
- `diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- `text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- `vae/minimax_h3_video_vae_fp16.safetensors`
- `vae/minimax_h3_audio_vae_fp32.safetensors`
