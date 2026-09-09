# Course audio (Menschen A1) — setup

The app's new **📚 Course** section plays these files. They are copyrighted
course material, so they live here locally and are **not** committed to git.

## 1 · Download

Source folder (shared link):

    https://drive.google.com/drive/folders/1rnUPDhwmGJlHjo7_Mjulp-ML0AoC2p10

Option A — browser: open the link, download the `*.mp3` files, copy them
into this folder (`course_audio/` next to `index.html`).

Option B — terminal (needs `gdown`: `pip install gdown`):

    cd /home/deck/Downloads/Dutch_App/course_audio
    gdown --folder "https://drive.google.com/drive/folders/1rnUPDhwmGJlHjo7_Mjulp-ML0AoC2p10"

Filenames must stay as-is (e.g. `01 Lektion 1, Hoeren, 2.mp3`) — the clip
builder and the sample `server/data/clips_course.json` reference them.

## 2 · Build the clips file

    python3 scripts/build_course_clips.py

This scans `*.mp3` (+ `.m4a/.ogg/.wav`), probes durations with `ffprobe`,
and writes `server/data/clips_course.json` (+ manifest entry).

## 3 · (Optional) Add transcripts for real quizzes

Without a transcript a clip still plays, but the quiz is a
"🎧 Listen and repeat / I listened (+5 XP)" self-check card.

For full listening/cloze quizzes, add a sidecar text file per mp3
(same basename):

    "01 Lektion 1, Hoeren, 2.txt"       German transcript
    "01 Lektion 1, Hoeren, 2.en.txt"    English translation (optional)
    "01 Lektion 1, Hoeren, 2.ar.txt"    Arabic translation (optional)

Then re-run the builder. Tip: generate a first draft with Whisper and
fix it by hand:

    whisper "course_audio/01 Lektion 1, Hoeren, 2.mp3" --language de --model tiny

## 4 · Serve / app packaging

- Web: serve the repo root so `course_audio/` resolves next to
  `index.html` (any static server works).
- Android WebView: the page URL must be able to reach the files — either
  host them (https) and rebuild with `--base-url https://…/course_audio`,
  or copy the folder into the APK assets and adjust the base URL.
