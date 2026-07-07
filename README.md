# Avatar Tax

A Remotion-based talking-head/avatar editor.

## Run locally

```bash
cd "/Users/anas/x/long form yt/avatar tax"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd renderer
npm install
cd ..
python avatar_tax_gui.py
```

## Run on Windows

This checkout has a local `.venv` with WhisperX installed. Start the app with:

```bat
run_avatar_tax.bat
```

## Script-first sync (recommended)

Put the voiceover script next to each avatar video as `<videoname>.txt` (or `.md`)
inside `avatars/`. The app then:

1. Plans from the exact written text (clean numbers for stat counters and charts).
2. Uses WhisperX only for word timing, aligning every script sentence to the
   audio, so each overlay/image starts when its point is spoken and holds until
   it finishes.

Without a script file, the app falls back to transcript-only planning.

## What it builds

- Uses one avatar/talking-head video as the base.
- Adds smooth punch-in/punch-out camera moves.
- Adds title cards, short text hits, animated data visuals (stat counters, bar
  charts, donut charts), optional Serper image inserts, and SFX.
- Writes Remotion data to `renderer/public/avatar_plan.json`.
- Creates a zip package in `zips/`.
