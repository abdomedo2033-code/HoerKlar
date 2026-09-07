#!/bin/sh
# Deck ingest worker launcher (no systemd needed).
# Starts the poll loop; run at login via ~/.config/autostart/hoerklar-worker.desktop
cd /home/deck/Downloads/Dutch_App || exit 1
export API_BASE="${API_BASE:-https://hoerklar-api.onrender.com}"
export HK_WORKDIR="${HK_WORKDIR:-/home/deck/Downloads/Dutch_App/_clipcache_ingest}"
export HK_DEFAULT_CEFR="${HK_DEFAULT_CEFR:-A2}"
# Whisper model cache + proxy-safe env (see scripts/add_video.py)
# NOTE: proxies must be fully unset — direct connection works, and any
# in-process lib (httpx/urllib) chokes on the SOCKS proxy without socksio.
unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
export HF_HOME=/var/cache/huggingface
mkdir -p "$HK_WORKDIR"
LOG="$HK_WORKDIR/worker.log"
# HF cache must be writable; fall back to the user cache otherwise.
if ! mkdir -p "$HF_HOME" 2>/dev/null || ! touch "$HF_HOME/.w" 2>/dev/null; then
  export HF_HOME=/home/deck/.cache/huggingface
  mkdir -p "$HF_HOME"
  echo "[launcher] $HF_HOME not writable — using $HF_HOME" >>"$LOG" 2>/dev/null || true
else
  rm -f "$HF_HOME/.w"
fi
# Warmup (network ON): prefetch the Whisper model so jobs never hit a
# cold cache while HF_HUB_OFFLINE=1 below. Failure is non-fatal — logged.
echo "[launcher] warming Whisper model into $HF_HOME ..."
HF_HUB_OFFLINE=0 /home/deck/whisperenv/bin/python -c \
  "from faster_whisper import WhisperModel; import os; WhisperModel(os.environ.get('HK_WHISPER_MODEL','tiny'), device='cpu', compute_type='int8'); print('[launcher] whisper warmup OK')" >>"$LOG" 2>&1 \
  || echo "[launcher] whisper warmup FAILED (jobs with subtitles still work; Whisper fallback needs network once)" >>"$LOG"
export HF_HUB_OFFLINE=1
echo "[launcher] starting worker -> $API_BASE (log $LOG)"
while true; do
  /home/deck/whisperenv/bin/python worker/worker.py >>"$LOG" 2>&1
  echo "[launcher] worker exited $? — restarting in 15s" >>"$LOG"
  sleep 15
done
