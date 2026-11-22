#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${WORKSPACE:-/workspace}"
export WORKSPACE
mkdir -p "$WORKSPACE"/{models,input,output,user,logs,mvpipe} /run/mvpipe /run/sshd
for category in checkpoints diffusion_models text_encoders vae loras latent_upscale_models model_patches; do
    mkdir -p "$WORKSPACE/models/$category"
done
printf 'PATH="/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"\n' > /etc/environment
grep -qF 'export PATH=/opt/venv/bin:$PATH' /root/.bashrc \
    || printf '\nexport PATH=/opt/venv/bin:$PATH\n' >> /root/.bashrc
mkdir -p /root/.ssh
chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
add_keys() {
    local key
    while IFS= read -r key || [ -n "$key" ]; do
        key="${key%$'\r'}"
        case "$key" in ''|\#*) continue;; esac
        grep -qxF "$key" /root/.ssh/authorized_keys || printf '%s\n' "$key" >> /root/.ssh/authorized_keys
    done
}
if [ -n "${PUBLIC_KEY:-}" ]; then printf '%s\n' "$PUBLIC_KEY" | add_keys; fi
if [ -f "$WORKSPACE/mvpipe/authorized_keys" ]; then add_keys < "$WORKSPACE/mvpipe/authorized_keys"; fi
if [ -s /root/.ssh/authorized_keys ]; then
    ssh-keygen -A
    /usr/sbin/sshd -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no
    echo '[mvpipe] SSH ready (keys only).'
fi
if [ "${INSTALL_WORKSPACE_CONTROLS:-1}" = 1 ]; then
for action in start stop restart status; do
    target="$WORKSPACE/$action-comfyui.sh"
    if [ -f "$target" ] && ! grep -qF '/opt/mvpipe/scripts/control.py' "$target"; then
        mkdir -p "$WORKSPACE/backups/pre-image-controls"
        cp -n "$target" "$WORKSPACE/backups/pre-image-controls/" || true
    fi
    printf '#!/usr/bin/env bash\nexec /opt/venv/bin/python /opt/mvpipe/scripts/control.py %s\n' "$action" > "$target"
    chmod +x "$target"
done
fi
echo '[mvpipe] Starting one ComfyUI worker; model library: /workspace/models.'
exec /opt/venv/bin/python /opt/mvpipe/scripts/supervise.py
