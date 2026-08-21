# Self-Healing Docs-to-RAG Chatbot

End-to-end **Bright Data Scraper Studio** (`bdata`) pipeline: scrape → health-check → **real `bdata scraper heal`** → embed → OpenRouter RAG with citations.

**Pinned collector:** [`c_mt2z0drp1irsde3ydk`](https://brightdata.com/cp/scrapers/c_mt2z0drp1irsde3ydk)  
**Proof:** [`docs/proof_self_heal_transcript.txt`](docs/proof_self_heal_transcript.txt) · [`data/proof_bdata_run.json`](data/proof_bdata_run.json)  
**90s demo:** [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Bright Data](https://img.shields.io/badge/Bright%20Data-Scraper%20Studio-orange)
![Vector DB](https://img.shields.io/badge/VectorDB-Chroma-green)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-blue)

---

## Judge path (one command)

```bash
npm i -g @brightdata/cli && bdata login --api-key $BRIGHTDATA_API_KEY
pip install -r requirements.txt
# .env must set BRIGHTDATA_COLLECTOR_ID=c_mt2z0drp1irsde3ydk + OPENROUTER_API_KEY
python -m uvicorn chatbot.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 → confirm collector + engine in sidebar → **Break & self-heal** (timeline polls real phases) → ask a docs question with citations.

Studio-first (`SCRAPE_ALLOW_FALLBACK=0`). Unlocker/HTTP only as emergency fallback.

---

## Architecture

```
                              ┌────────────────────────┐
                              │  Docs Site (DuckDB)    │
                              └───────────┬────────────┘
                                          │
                                          ▼
                         ┌─────────────────────────────────┐
                         │   run_scraper.py (bdata CLI)   │
                         └────────────────┬────────────────┘
                                          │
                                          ▼
                         ┌─────────────────────────────────┐
                         │  health_check.py (Validation)   │
                         └───────┬─────────────────┬───────┘
                                 │                 │
                      UNHEALTHY  │                 │  HEALTHY
                                 ▼                 ▼
             ┌───────────────────────┐   ┌───────────────────────┐
             │ bdata scraper heal    │   │ last_known_good.json  │
             │ bdata scraper approve │   └───────────┬───────────┘
             └───────────┬───────────┘               │
                         │                           ▼
                         │               ┌───────────────────────┐
                         └──────────────►│ chunk_and_embed.py    │
                        (Retry Loop)     └───────────┬───────────┘
                                                     │
                                                     ▼
                                         ┌───────────────────────┐
                                         │  Chroma Vector DB     │
                                         └───────────┬───────────┘
                                                     │
                                                     ▼
                                         ┌───────────────────────┐
                                         │  RAG Chatbot (FastAPI)│
                                         │  + Source Citations   │
                                         └───────────────────────┘
```

---

## Setup

### 1. Prerequisites
- Python 3.10+
- Bright Data CLI:
  ```bash
  npm install -g @brightdata/cli
  bdata login --api-key YOUR_API_KEY
  ```

### 2. Install
```bash
git clone https://github.com/your-username/Web-Scraper-Self-Healing.git
cd Web-Scraper-Self-Healing
pip install -r requirements.txt
```

### 3. Environment
```bash
cp .env.example .env
```
```env
BRIGHTDATA_API_KEY=your_api_key_here
BRIGHTDATA_ZONE=cli_unlocker
BRIGHTDATA_COLLECTOR_ID=c_mt2z0drp1irsde3ydk
TARGET_URL=https://duckdb.org/docs/
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini
SCRAPE_ALLOW_FALLBACK=0
```

Create a collector (one-time) if you need a new one:
```bash
bdata scraper create https://duckdb.org/docs/current/ "Extract url, title, and main documentation content" --name docs-rag-self-heal --pretty
```

### 4. Prove heal locally
```bash
python scripts/heal_loop.py --mock-unhealthy
```
UI polls `GET /api/heal-status` while the timeline advances: Scrape → Health → Heal → Index.

2. Runs `scripts/heal_loop.py` to scrape, validate, self-heal, and embed vectors in ChromaDB.
3. Launches the FastAPI Chatbot app on `http://localhost:8000`.
4. Automatically opens the app in your default browser.

#### Handy Options for `start.py`:
- **Skip scraper run & start server immediately**: `python start.py --skip-heal`
- **Demo mock self-heal loop**: `python start.py --mock-unhealthy`
- **Custom port**: `python start.py --port 8080`

---

### Manual Step-by-Step Run (Optional)

#### Step 1: Run the Self-Healing Scraper Loop
```bash
python scripts/heal_loop.py
```

#### Step 2: Start the RAG Chatbot
```bash
python -m uvicorn chatbot.app:app --reload --port 8000
```
Open your browser to: **`http://localhost:8000`**

---

## Demo the self-heal feature

### Method A: UI (recommended for judges)
1. Open `http://127.0.0.1:8000`.
2. Confirm sidebar shows collector `c_mt2z0drp1irsde3ydk`.
3. Click **Break & self-heal**.
4. Watch the timeline: Scrape → Health (FAIL) → Heal → Index — driven by `GET /api/heal-status`.
5. Ask a docs question; show citations.

### Method B: Terminal
```bash
python scripts/heal_loop.py --mock-unhealthy
```
`--mock-unhealthy` only injects an empty first scrape. With a real collector + `bdata`, heal/approve/run are real.

Proof transcript: [`docs/proof_self_heal_transcript.txt`](docs/proof_self_heal_transcript.txt)

---

## GitHub Actions

`.github/workflows/scrape-and-heal.yml` runs on a schedule (every 6 hours) and via `workflow_dispatch`.

---

## License
MIT License.

