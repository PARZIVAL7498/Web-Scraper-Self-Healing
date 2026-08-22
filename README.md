<div align="center">

<img src="docs/self-healing-rag-banner.png" alt="SELF-HEALING-RAG" width="100%" />

# Self-Healing RAG

**When the DOM shifts, the answers should not die.**

[![Python](https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](#quick-start)
[![Bright Data](https://img.shields.io/badge/bright%20data-studio-FF6A00?style=for-the-badge)](https://brightdata.com)
[![Chroma](https://img.shields.io/badge/chroma-vector-10B981?style=for-the-badge)](https://www.trychroma.com)
[![FastAPI](https://img.shields.io/badge/fastapi-rag-009688?style=for-the-badge&logo=fastapi&logoColor=white)](#http-api)
[![MIT](https://img.shields.io/badge/license-MIT-22C55E?style=for-the-badge)](#license)

`scrape` → `health` → `heal` → `index` → `answer`

[Features](#features) · [Quick Start](#quick-start) · [Workflow](#workflow) · [Demo](#demo-the-heal) · [API](#http-api) · [CI](#github-actions)

</div>

Docs scrapers die the day a site ships a new layout. This repo is the extra life.

It watches the extract. If the payload comes back empty, it does **not** patch a CSS selector in Python. It calls a real Bright Data Scraper Studio heal on your collector, re-runs the scrape, re-indexes Chroma, and keeps the chatbot answering with citations.

Point it at any docs site. Swap OpenRouter / Gemini / OpenAI without touching app code. Launch from the UI, `python start.py`, or GitHub Actions every six hours.

---

## Features

<table>
<tr>
<td width="50%">

**Real Studio heal**  
Health FAIL runs `bdata scraper heal` + approve, then a Studio re-run. `--mock-unhealthy` only breaks the first scrape so you can demo the loop.

</td>
<td width="50%">

**Cited RAG**  
Chroma + `all-MiniLM-L6-v2`. Index first; live scrape only if that site is missing. Answers come with source titles and URLs.

</td>
</tr>
<tr>
<td width="50%">

**Live dual-URL compare**  
Scrape two docs sites, embed both, then get a side-by-side report with a coverage chart plus Markdown / PDF export.

</td>
<td width="50%">

**Demo UI**  
Sidebar shows collector, engine, chunks, and last heal. The timeline polls Scrape → Health → Heal → Index live.

</td>
</tr>
<tr>
<td width="50%">

**Studio-first CI**  
`SCRAPE_ALLOW_FALLBACK=0` by default. Actions re-scrapes every 6 hours and commits a healthy baseline.

</td>
<td width="50%">

**One command**  
`python start.py` copies `.env`, runs the heal loop, starts FastAPI, opens the browser. Windows: `run.bat` / `run.ps1`.

</td>
</tr>
</table>

---

## Quick Start

**Need:** Python 3.10+, Node (for the Bright Data CLI), a [Bright Data](https://brightdata.com) collector, and an [OpenRouter](https://openrouter.ai) key (Gemini or OpenAI also work).

### 1. Install

```bash
git clone https://github.com/PARZIVAL7498/Web-Scraper-Self-Healing.git
cd Web-Scraper-Self-Healing
pip install -r requirements.txt
npm install -g @brightdata/cli
bdata login --api-key $BRIGHTDATA_API_KEY
```

### 2. Configure

```bash
cp .env.example .env
```

```env
BRIGHTDATA_API_KEY=your_api_key_here
BRIGHTDATA_COLLECTOR_ID=c_your_collector_id_here
TARGET_URL=https://duckdb.org/docs/
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini
SCRAPE_ALLOW_FALLBACK=0
```

No collector yet?

```bash
bdata scraper create https://duckdb.org/docs/current/ \
  "Extract url, title, and main documentation content" \
  --name docs-rag-self-heal --pretty
```

Put the returned `c_*` id in `BRIGHTDATA_COLLECTOR_ID`.

### 3. Run

```bash
python start.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Confirm collector + engine in the sidebar. Ask a docs question.

| Shortcut | Command |
| --- | --- |
| UI only | `python start.py --skip-heal` |
| Demo a broken scrape then heal | `python start.py --mock-unhealthy` |
| Windows | `.\run.ps1` or `run.bat` |

---

## Workflow

### System

```mermaid
flowchart LR
  site[Docs site] --> scrape[run_scraper.py]
  scrape --> studio[Bright Data Studio]
  studio --> health[health_check.py]
  health -->|FAIL| heal["bdata scraper heal"]
  heal --> scrape
  health -->|PASS| baseline[last_known_good.json]
  baseline --> embed[chunk_and_embed.py]
  embed --> chroma[(Chroma docs_rag)]
  chroma --> api[FastAPI]
  api --> chat[Cited RAG]
  api --> compare[Live compare]
```

### Heal loop

```mermaid
flowchart TD
  trigger[start.py / UI / Actions] --> scrape[Scrape collector]
  scrape --> health{Health check}
  health -->|PASS| save[Write last_known_good.json]
  health -->|FAIL and retries left| heal["bdata scraper heal + approve"]
  heal --> scrape
  health -->|FAIL after 2 retries| dead[Exit 1 / CI red]
  save --> embed[chunk_and_embed.py]
  embed --> chroma[(Chroma)]
  chroma --> ui[Chatbot answers with citations]
```

Gates that fail a scrape: empty payload, a page under 30 characters, or a same-domain page-count collapse vs `data/last_known_good.json`. Unlocker/HTTP only if `SCRAPE_ALLOW_FALLBACK=1`.

The UI timeline is this loop. It polls `GET /api/heal-status` while `heal_loop.py` writes `data/heal_job_status.json`.

### RAG chat

```mermaid
sequenceDiagram
  actor User
  participant UI
  participant API as FastAPI
  participant Chroma
  participant Studio as Bright Data
  participant LLM as OpenRouter / Gemini / OpenAI

  User->>UI: question + docs URL
  UI->>API: POST /api/chat
  API->>Chroma: query by site tag
  alt site not indexed
    API->>Studio: scrape
    Studio-->>API: pages
    API->>Chroma: embed chunks
  end
  API->>LLM: context + question
  LLM-->>UI: answer + citations
```

LLM order: OpenRouter → Gemini → OpenAI → local extract.

### Dual-URL compare

```mermaid
flowchart LR
  a[Docs A] --> sa[Scrape + health]
  b[Docs B] --> sb[Scrape + health]
  sa --> ea[Embed A]
  sb --> eb[Embed B]
  ea --> synth[Comparative synthesis]
  eb --> synth
  synth --> report[Report + chart + PDF]
```

### Launch path

```mermaid
flowchart LR
  start[python start.py] --> env[Copy .env if missing]
  env --> loop[heal_loop.py]
  loop --> serve[uvicorn chatbot.app]
  serve --> browser[http://127.0.0.1:8000]
```

---

## Demo the heal

`--mock-unhealthy` empties the **first** scrape only. Heal, approve, and the retry are live Studio calls when `bdata` is on PATH and the collector is real.

**From the UI**

1. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).
2. Confirm the sidebar collector id.
3. Click **Break & self-heal**.
4. Watch Health FAIL flip to Heal → Index.
5. Ask a docs question and show the citations.

**From the terminal**

```bash
python scripts/heal_loop.py --mock-unhealthy
```

90-second shot list: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

---

## Commands

| You want | Run |
| --- | --- |
| Full launch | `python start.py` |
| UI only | `python start.py --skip-heal` |
| Demo heal | `python start.py --mock-unhealthy` |
| Custom port | `python start.py --port 8080` |
| Loop only | `python scripts/heal_loop.py` |
| Loop, no `bdata` | `python scripts/heal_loop.py --mock` |
| One URL | `python scripts/run_scraper.py --url https://duckdb.org/docs/` |
| Health only | `python scripts/health_check.py` |
| Re-embed | `python scripts/chunk_and_embed.py` |

`start.py` also takes `--host`, `--no-reload`, `--no-browser`.

---

## Environment

| Variable | Required | What it does |
| --- | --- | --- |
| `BRIGHTDATA_API_KEY` | live Studio | login, scrape, heal |
| `BRIGHTDATA_COLLECTOR_ID` | yes | Scraper Studio `c_*` |
| `BRIGHTDATA_ZONE` | no | Unlocker zone (`cli_unlocker`) |
| `TARGET_URL` | no | default `https://duckdb.org/docs/` |
| `SCRAPE_ALLOW_FALLBACK` | no | `0` Studio only · `1` emergency Unlocker/HTTP |
| `OPENROUTER_API_KEY` | recommended | primary LLM |
| `OPENROUTER_MODEL` | no | default `openai/gpt-4o-mini` |
| `GEMINI_API_KEY` | no | fallback LLM |
| `OPENAI_API_KEY` | no | fallback LLM |
| `PORT` | no | default `8000` |

---

## HTTP API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/` | chat + compare UI |
| `GET` | `/api/status` | chunks, baseline, collector, engine, LLM |
| `GET` | `/api/heal-status` | live heal phase for the timeline |
| `POST` | `/api/chat` | `{ query, url?, top_k? }` → answer + citations |
| `POST` | `/api/trigger-scrape` | `{ mock_unhealthy? }` starts the loop |
| `POST` | `/api/scrape-and-compare` | `{ url_a, url_b, topic? }` → report + scores |

---

## GitHub Actions

Two workflows:

| Workflow | When | What |
| --- | --- | --- |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | push / pull request | `compileall` on `start.py`, `chatbot/`, `scripts/` |
| [`.github/workflows/scrape-and-heal.yml`](.github/workflows/scrape-and-heal.yml) | every 6 hours + manual | scrape → health → heal → index → commit baseline |

```mermaid
flowchart LR
  cron[Every 6 hours] --> job[heal_loop.py]
  click[workflow_dispatch] --> job
  job -->|PASS| commit[Commit last_known_good.json]
  job -->|FAIL| red[Job fails]
```

**Secrets:** `BRIGHTDATA_API_KEY`, `BRIGHTDATA_COLLECTOR_ID`  
**Optional secrets:** `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`  
**Optional vars:** `TARGET_URL`, `BRIGHTDATA_ZONE`, `SCRAPE_ALLOW_FALLBACK`

Manual run can set `mock_mode` or `mock_unhealthy`. Scheduled runs require the Bright Data secrets.

---

## Project layout

```
.
├── start.py                         # env → heal loop → uvicorn
├── run.bat / run.ps1                # Windows launchers
├── chatbot/
│   ├── app.py                       # FastAPI: RAG, compare, heal status
│   └── static/                      # UI
├── scripts/
│   ├── run_scraper.py               # Studio-first scrape
│   ├── health_check.py              # empty / baseline gates
│   ├── heal_loop.py                 # scrape → check → heal → index
│   └── chunk_and_embed.py           # Chroma indexing
├── data/                            # scrapes, baseline, heal status, Chroma
├── docs/
│   ├── self-healing-rag-banner.png  # README banner
│   └── DEMO_SCRIPT.md
└── .github/workflows/
    ├── ci.yml
    └── scrape-and-heal.yml
```

---

