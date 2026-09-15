FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg ca-certificates git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev

# yt-dlp + automatic YouTube Proof-of-Origin token provider.
# YouTube currently enforces PO Tokens for some clients; bgutil can generate
# them locally and expose them to yt-dlp on 127.0.0.1:4416.
RUN python3 -m pip install --break-system-packages -U yt-dlp bgutil-ytdlp-pot-provider==2.0.0

# Build the local bgutil HTTP provider (same container, no public port).
RUN git clone --depth 1 --branch 2.0.0 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
  && cd /opt/bgutil/server \
  && npm ci \
  && npx tsc

COPY . .

RUN mkdir -p /app/downloads

EXPOSE 10000

CMD ["bash", "-lc", "node /opt/bgutil/server/build/main.js --host 127.0.0.1 --port 4416 & exec npm start"]
