# mvpipe pod image: ComfyUI (pinned) + MiniMax H3 + the custom nodes mvpipe needs.
# Everything big and slow to change lives in /opt (container disk, rebuilt with the image).
# Everything the user owns (models, outputs, logs) lives on the network volume at /workspace.
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

# Pins. Change them here (or with --build-arg) and rebuild; nothing is fetched "latest" at boot.
ARG COMFYUI_REF=v0.37.0
ARG TORCH_VERSION=2.11.0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128
ARG FFMPEG_URL=https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WORKSPACE=/workspace \
    COMFYUI_DIR=/opt/ComfyUI \
    PATH=/opt/venv/bin:$PATH

# build-essential: Triton compiles small helpers with gcc at run time.
# libgl1/libglib2.0-0: OpenCV (pulled in by the custom nodes).
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev build-essential \
        git curl ca-certificates rsync openssh-server xz-utils procps \
        libgl1 libglib2.0-0 \
        tree htop nano less jq unzip tmux wget ncdu \
    && rm -rf /var/lib/apt/lists/*

# A current static ffmpeg (the pod's apt ffmpeg 4.4 lacks -fps_mode).
RUN curl -fsSL "$FFMPEG_URL" -o /tmp/ffmpeg.tar.xz \
    && mkdir /tmp/ffmpeg && tar -xJf /tmp/ffmpeg.tar.xz -C /tmp/ffmpeg --strip-components=1 \
    && install -m 0755 /tmp/ffmpeg/ffmpeg /tmp/ffmpeg/ffprobe /usr/local/bin/ \
    && rm -rf /tmp/ffmpeg /tmp/ffmpeg.tar.xz \
    && ffmpeg -version | head -1

RUN python3 -m venv /opt/venv \
    && pip install "torch==${TORCH_VERSION}" torchvision torchaudio --index-url "${TORCH_INDEX}"

# ComfyUI at a pinned release.
RUN git clone -q https://github.com/comfyanonymous/ComfyUI.git "$COMFYUI_DIR" \
    && git -C "$COMFYUI_DIR" checkout -q "$COMFYUI_REF" \
    && pip install -r "$COMFYUI_DIR/requirements.txt"

# Custom nodes, each at a pinned commit (config/custom_nodes.txt: "<git url> <commit>").
COPY config/custom_nodes.txt /opt/mvpipe/custom_nodes.txt
RUN set -eux; cd "$COMFYUI_DIR/custom_nodes"; \
    while read -r url ref; do \
        case "$url" in ''|\#*) continue;; esac; \
        d="$(basename "$url" .git)"; \
        git init -q "$d"; git -C "$d" remote add origin "$url"; \
        git -C "$d" fetch -q --depth 1 origin "$ref"; git -C "$d" checkout -q FETCH_HEAD; \
        if [ -f "$d/requirements.txt" ]; then pip install -r "$d/requirements.txt"; fi; \
        echo "$d $(git -C "$d" rev-parse HEAD)" >> /opt/mvpipe/custom_nodes.lock; \
    done < /opt/mvpipe/custom_nodes.txt

# JupyterLab is optional at run time (ENABLE_JUPYTER=1) but cheap to include.
RUN pip install jupyterlab

# nvitop: GPU monitor. It lives in the venv (the system Python refuses pip installs, PEP 668),
# and is linked into /usr/local/bin so it works in any shell, SSH or Jupyter terminal.
RUN pip install nvitop && ln -s /opt/venv/bin/nvitop /usr/local/bin/nvitop

# Fail the build if the torch install was disturbed by a node's requirements.
RUN python -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda)" \
    && pip check || true

COPY config/extra_model_paths.yaml config/models.json /opt/mvpipe/
COPY scripts/ /opt/mvpipe/scripts/
COPY start.sh /start.sh
RUN chmod +x /start.sh /opt/mvpipe/scripts/*.py

# 8188+ ComfyUI (one per GPU), 8888 Jupyter, 22 sshd. Declare them again in the RunPod template.
EXPOSE 22 8188 8189 8190 8191 8888
WORKDIR /workspace
CMD ["/start.sh"]
