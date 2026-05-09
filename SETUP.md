# PitchPoint — Local Setup

Step-by-step to run PitchPoint on a fresh machine.

## Prerequisites

- **Python 3.10+** (`python3 --version`)
- **Node 18+** (`node --version`)
- **Git**

## 1. Clone the repo

```bash
git clone https://github.com/skylarsoon/PitchPoint.git
cd PitchPoint
```

## 2. Get the release code

Until [PR #1](https://github.com/skylarsoon/PitchPoint/pull/1) is merged into `main`:

```bash
git checkout release-submission-2026-05-09-1258
git pull
```

Once merged, `main` is enough — skip the checkout.

## 3. Backend — Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
```

## 4. Frontend — Node

```bash
npm install
```

## 5. API keys (optional for the demo)

The 5 demo addresses are **pre-cached in the repo** — they work with **no API keys**. Skip this step if you just want to demo.

For arbitrary addresses:

```bash
cp .env.example .env
```

Fill in:

- `GOOGLE_MAPS_API_KEY` — Geocoding, Static Maps, Solar, Address Validation, Street View
- `OPENAI_API_KEY` — synthesizer LLM + multi-shot pitch
- `GEMINI_API_KEY` — alternate vision path / synthesizer fallback
- `VITE_GOOGLE_MAPS_API_KEY` — Places autocomplete in the address input

## 6. Run it (two terminals)

**Terminal A — backend on :8000**

```bash
source .venv/bin/activate
cd server
uvicorn api:app --port 8000 --reload
```

**Terminal B — frontend on :5173**

```bash
npm run dev
```

## 7. Test it

Open **http://localhost:5173** and paste any of the 5 cached demo addresses (instant, no API hits):

| Address | Expected sqft |
|---|---:|
| 6310 Laguna Bay Court, Houston, TX 77041 | 4,186 |
| 1612 S Canton Ave, Springfield, MO 65802 | 2,757 |
| 3561 E 102nd Ct, Thornton, CO 80229 | 2,081 |
| 3820 E Rosebrier St, Springfield, MO 65809 | 5,566 |
| 1261 20th Street, Newport News, VA 23607 | 6,118 |

Live addresses (cache miss) take ~30–60s and require API keys from step 5.

## Common gotchas

- **Apple Silicon + geopandas/fiona pip errors** → `brew install gdal proj` first, then re-run `pip install`.
- **Port already in use** → `lsof -ti tcp:8000 | xargs kill -9` (or `5173`).
- **Backend can't find modules** → confirm the venv is activated and `uvicorn` is launched from inside the `server/` directory (some imports are relative).
- **CORS errors in browser** → make sure the frontend is on `:5173`. The backend only allows that origin.
