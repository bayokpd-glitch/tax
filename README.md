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

## What it builds

- Uses one avatar/talking-head video as the base.
- Adds smooth punch-in/punch-out camera moves.
- Adds title cards, short text hits, side/bottom overlays, optional Serper image inserts, and SFX.
- Writes Remotion data to `renderer/public/avatar_plan.json`.
- Creates a zip package in `zips/`.
