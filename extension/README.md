# HörKlar importer (Chrome/Edge extension) — your pc does everything

Desktop browsers can't touch YouTube (locked). This tiny extension is *allowed*
through that lock, so your pc fetches subtitles/audio itself. No server, no Deck.

## Install (2 minutes, once)

1. Open `chrome://extensions` (or `edge://extensions`)
2. Turn on **Developer mode** (top-right switch)
3. Click **Load unpacked** → pick this `extension/` folder
4. Open your HörKlar site — the ＋ Add video button now uses your pc first

## What it does

- **Subtitled videos:** instant — subtitles flow pc → quizzes, ~30s
- **No-subtitle videos:** the extension saves the audio track to Downloads,
  you pick it once in the card, and your pc transcribes it locally
  (first run downloads a ~40MB ear model, then cached)
- **YouTube pages:** a ＋ HörKlar button under the title saves the link;
  open HörKlar and it's ready to build

## Privacy

Everything runs locally: subtitles/audio go extension → page directly.
Nothing is uploaded anywhere, ever. Permissions used: youtube.com +
googlevideo.com (reading), downloads (saving the audio you asked for).
