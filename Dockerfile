FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg libglib2.0-0 libgl1 git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip3 install --break-system-packages faster-whisper==1.1.1 "yt-dlp[default]" opencv-python-headless==4.11.0.86 bgutil-ytdlp-pot-provider==2.0.0
WORKDIR /opt/bgutil
RUN git clone --depth 1 --branch 2.0.0 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git . \
 && cd server \
 && npm ci \
 && npx tsc
WORKDIR /app
COPY package.json server.js pipeline.py index.html ./
RUN npm install --omit=dev
ENV PORT=10000 WHISPER_MODEL=small WHISPER_DEVICE=cpu WHISPER_COMPUTE_TYPE=int8 \
    BGUTIL_SCRIPT=/opt/bgutil/server/build/generate_once.js
EXPOSE 10000
CMD ["node","server.js"]
