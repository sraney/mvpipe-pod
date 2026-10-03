#!/usr/bin/env bash
# mvpipe pod boot script (container entrypoint). Order matters; every step is non-fatal
# except the workers, and every step logs one line so the log tells the story.
set -u

WORKSPACE="${WORKSPACE:-/workspace}"
COMFYUI_DIR="${COMFYUI_DIR:-/opt/ComfyUI}"
BASE_PORT="${COMFYUI_BASE_PORT:-8188}"
LOGS="$WORKSPACE/logs"
log() { echo "[mvpipe-boot $(date -u +%H:%M:%S)] $*"; }

mkdir -p "$WORKSPACE"/{models,input,output,temp,user,logs,mvpipe}
for d in diffusion_models text_encoders vae loras latent_upscale_models model_patches checkpoints; do
    mkdir -p "$WORKSPACE/models/$d"
done

# 1. Make the RunPod variables visible to SSH/Jupyter shells (they only exist in PID 1's environment).
#    Secrets (tokens, keys) are deliberately not copied.
printenv | grep -E '^(RUNPOD_|CUDA_|NVIDIA_|MVPIPE_)' | grep -v '^NVIDIA_REQUIRE' \
    | sed -E 's/^([^=]+)=(.*)$/export \1="\2"/' > /etc/rp_environment
# SSH/Jupyter shells do not inherit the image's PATH: put the venv first so `python`, `pip` and ComfyUI's packages resolve.
# Interactive shells get it through rp_environment (sourced from .bashrc). Plain remote commands
# (`ssh host 'python ...'`) skip .bashrc, so also write /etc/environment, which sshd's PAM stack reads for every session.
echo 'export PATH=/opt/venv/bin:$PATH' >> /etc/rp_environment
echo 'PATH="/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"' > /etc/environment
chmod 600 /etc/rp_environment
grep -qs rp_environment /root/.bashrc || echo '[ -f /etc/rp_environment ] && . /etc/rp_environment' >> /root/.bashrc

# 2. SSH keys and sshd (optional fallback transport).
#    Keys come from PUBLIC_KEY (one per line) and from an optional file on the volume,
#    $WORKSPACE/mvpipe/authorized_keys (one per line, # comments allowed). A key placed in that file
#    once is trusted by every future pod. Existing lines are never duplicated or removed.
mkdir -p /root/.ssh /run/sshd && chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys
add_keys() {  # reads public keys on stdin
    local k
    while IFS= read -r k || [ -n "$k" ]; do
        k="${k%$'\r'}"
        case "$k" in ''|\#*) continue;; esac
        grep -qxF "$k" /root/.ssh/authorized_keys || echo "$k" >> /root/.ssh/authorized_keys
    done
}
[ -n "${PUBLIC_KEY:-}" ] && printf '%s\n' "$PUBLIC_KEY" | add_keys
[ -f "$WORKSPACE/mvpipe/authorized_keys" ] && add_keys < "$WORKSPACE/mvpipe/authorized_keys"
chmod 600 /root/.ssh/authorized_keys
if [ -s /root/.ssh/authorized_keys ]; then
    ssh-keygen -A >/dev/null 2>&1
    /usr/sbin/sshd && log "sshd started on port 22 ($(grep -c . /root/.ssh/authorized_keys) key(s))" || log "sshd failed to start"
else
    log "no SSH keys (PUBLIC_KEY or $WORKSPACE/mvpipe/authorized_keys): sshd not started (ComfyUI over HTTPS is the main path)"
fi

# 3. Model set check. Reports only; a missing file never stops boot.
python /opt/mvpipe/scripts/verify_models.py --models-dir "$WORKSPACE/models" --json "$LOGS/model_check.json" \
    2>&1 | sed 's/^/[models] /'

# 4. One ComfyUI worker per GPU, pinned with CUDA_VISIBLE_DEVICES, restarted if it dies.
GPUS="${MVPIPE_GPU_COUNT:-$(nvidia-smi -L 2>/dev/null | wc -l)}"
[ "$GPUS" -ge 1 ] 2>/dev/null || { log "no GPU found: starting one CPU-only worker"; GPUS=1; CPU_ARG="--cpu"; }

run_worker() {
    local i="$1" port=$((BASE_PORT + $1))
    while true; do
        log "worker $i starting on port $port"
        CUDA_VISIBLE_DEVICES="$i" python "$COMFYUI_DIR/main.py" \
            --listen 0.0.0.0 --port "$port" \
            --extra-model-paths-config /opt/mvpipe/extra_model_paths.yaml \
            --input-directory "$WORKSPACE/input" --output-directory "$WORKSPACE/output" \
            --temp-directory "$WORKSPACE/temp/gpu$i" --user-directory "$WORKSPACE/user" \
            --disable-auto-launch ${CPU_ARG:-} ${COMFYUI_EXTRA_ARGS:-} \
            >> "$LOGS/comfyui-gpu$i.log" 2>&1
        log "worker $i exited (code $?), restarting in 5 s"
        sleep 5
    done
}
for ((i = 0; i < GPUS; i++)); do run_worker "$i" & done
log "$GPUS worker(s) launched; first load from the volume can take 7-15 minutes"

# 5. JupyterLab, optional, always with a token.
if [ "${ENABLE_JUPYTER:-0}" = "1" ]; then
    if [ -z "${JUPYTER_TOKEN:-}" ]; then
        JUPYTER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
        ( umask 077; echo "$JUPYTER_TOKEN" > "$WORKSPACE/logs/jupyter_token.txt" )
        log "no JUPYTER_TOKEN set: generated one, saved in $WORKSPACE/logs/jupyter_token.txt"
    fi
    ( cd "$WORKSPACE" && exec jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root \
        --ServerApp.token="$JUPYTER_TOKEN" --ServerApp.root_dir="$WORKSPACE" \
        >> "$LOGS/jupyter.log" 2>&1 ) &
    log "JupyterLab started on port 8888"
fi

# 6. mvpipe's transport agent, if it has been placed on the volume.
if [ -f "$WORKSPACE/mvpipe/pod_agent.py" ]; then
    ( cd "$WORKSPACE/mvpipe" && while true; do python pod_agent.py >> "$LOGS/pod_agent.log" 2>&1; sleep 5; done ) &
    log "pod_agent.py started"
else
    log "no $WORKSPACE/mvpipe/pod_agent.py yet: agent not started"
fi

trap 'log "stopping"; kill $(jobs -p) 2>/dev/null; exit 0' TERM INT
wait
