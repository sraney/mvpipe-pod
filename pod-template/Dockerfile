FROM nvidia/cuda:13.0.2-runtime-ubuntu24.04@sha256:6a0e31b59e70890446f2c17356d6efc0d54260090a8c63d6ca7c2ad049db95d2

ARG COMFYUI_COMMIT=a277b5bf213e8a44fa34817b7770b54f86ef4cea
ARG IMAGE_REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/sraney/mvpipe-pod" \
      org.opencontainers.image.revision=$IMAGE_REVISION \
      org.opencontainers.image.description="ComfyUI 0.46.0 with the validated MiniMax H3 runtime"
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WORKSPACE=/workspace \
    COMFYUI_DIR=/opt/ComfyUI \
    COMFYUI_PORT=8188 \
    PATH=/opt/venv/bin:$PATH \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev build-essential \
        git ca-certificates curl ffmpeg openssh-server tini \
        libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
COPY config/requirements.lock /opt/mvpipe/requirements.lock
RUN pip install --extra-index-url https://download.pytorch.org/whl/cu130 \
        -r /opt/mvpipe/requirements.lock
RUN git init -q "$COMFYUI_DIR" \
    && git -C "$COMFYUI_DIR" remote add origin https://github.com/Comfy-Org/ComfyUI.git \
    && git -C "$COMFYUI_DIR" fetch -q --depth 1 origin "$COMFYUI_COMMIT" \
    && git -C "$COMFYUI_DIR" checkout -q FETCH_HEAD \
    && test "$(git -C "$COMFYUI_DIR" rev-parse HEAD)" = "$COMFYUI_COMMIT"
COPY config/custom_nodes.txt /opt/mvpipe/custom_nodes.txt
RUN set -eu; cd "$COMFYUI_DIR/custom_nodes"; \
    while read -r url ref; do \
        case "$url" in ''|\#*) continue;; esac; \
        d="$(basename "$url" .git)"; \
        git init -q "$d"; git -C "$d" remote add origin "$url"; \
        git -C "$d" fetch -q --depth 1 origin "$ref"; \
        git -C "$d" checkout -q FETCH_HEAD; \
        test "$(git -C "$d" rev-parse HEAD)" = "$ref"; \
        if [ -f "$d/requirements.txt" ]; then \
            pip install -c /opt/mvpipe/requirements.lock -r "$d/requirements.txt"; \
        fi; \
        echo "$d $ref" >> /opt/mvpipe/custom_nodes.lock; \
    done < /opt/mvpipe/custom_nodes.txt
RUN pip install -c /opt/mvpipe/requirements.lock -r "$COMFYUI_DIR/requirements.txt" \
    && pip check \
    && python -c "import torch; assert torch.__version__ == '2.11.0+cu130'; assert torch.version.cuda == '13.0'"
COPY config/extra_model_paths.yaml config/models.json /opt/mvpipe/
COPY scripts/ /opt/mvpipe/scripts/
COPY validation/ /opt/mvpipe/validation/
COPY start.sh /start.sh
RUN chmod +x /start.sh /opt/mvpipe/scripts/*.py
EXPOSE 22 8188
WORKDIR /workspace
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('COMFYUI_PORT','8188')+'/system_stats',timeout=4).read()"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/start.sh"]
