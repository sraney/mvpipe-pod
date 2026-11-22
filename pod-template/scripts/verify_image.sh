#!/usr/bin/env bash
set -euo pipefail
python /opt/mvpipe/scripts/restore_nodes.py
mkdir -p /workspace/user
python /opt/ComfyUI/main.py --cpu --enable-manager --listen 127.0.0.1 --port 8188 \
    --extra-model-paths-config /run/mvpipe/extra_model_paths.yaml \
    --user-directory /workspace/user --disable-auto-launch > /tmp/comfyui-image-check.log 2>&1 &
worker=$!
cleanup() {
    result=$?
    kill "$worker" 2>/dev/null || true
    wait "$worker" 2>/dev/null || true
    if [ "$result" -ne 0 ]; then cat /tmp/comfyui-image-check.log; fi
    exit "$result"
}
trap cleanup EXIT
python /opt/mvpipe/scripts/check_nodes.py --wait 180
python /opt/mvpipe/scripts/check_profile.py
