#!/bin/sh
# Deck ingest worker launcher (no systemd needed).
# Starts the poll loop; run at login via ~/.config/autostart/hoerklar-worker.desktop
cd /home/deck/Downloads/Dutch_App || exit 1
export API_BASE="${API_BASE:-https://hoerklar-api.onrender.com}"
export HK_WORKDIR="${HK_WORKDIR:-/home/deck/Downloads/Dutch_App/_clipcache_ingest}"
export HK_DEFAULT_CEFR="${HK_DEFAULT_CEFR:-A2}"
# Whisper model cache + proxy-safe env (see scripts/add_video.py)
export HF_HOME=/var/cache/huggingface
export HF_HUB_OFFLINE=1
mkdir -p "$HK_WORKDIR"
LOG="$HK_WORKDIR/worker.log"
echo "[launcher] starting worker -> $API_BASE (log $LOG)"
while true; do
  /home/deck/whisperenv/bin/python worker/worker.py >>"$LOG" 2>&1
  echo "[launcher] worker exited $? — restarting in 15s" >>"$LOG"
  sleep 15
done
