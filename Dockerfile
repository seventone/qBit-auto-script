FROM linuxserver/qbittorrent:latest

# 1. 安装Python3、pip3（系统级）
RUN apk update && \
    apk add --no-cache python3 py3-pip && \
    # 2. 创建虚拟环境（路径：/opt/venv，容器内固定路径）
    python3 -m venv /opt/venv && \
    # 3. 在虚拟环境中安装requests（用虚拟环境的pip）
    /opt/venv/bin/pip install --no-cache-dir requests && \
    # 4. 清理缓存
    rm -rf /var/cache/apk/*

# 5. 设置环境变量，让系统优先使用虚拟环境的Python（可选，方便手动调用）
ENV PATH="/opt/venv/bin:$PATH"
