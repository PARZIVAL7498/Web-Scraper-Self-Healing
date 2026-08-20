# ⚡ Self-Healing Docs-to-RAG Chatbot

An end-to-end self-healing documentation scraper and RAG chatbot built with **Bright Data Scraper Studio CLI (`bdata`)**, **ChromaDB**, **FastAPI**, and **GitHub Actions**.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Bright Data](https://img.shields.io/badge/Bright%20Data-Scraper%20Studio-orange)
![Vector DB](https://img.shields.io/badge/VectorDB-Chroma-purple)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-blue)

---

## 📐 Architecture Diagram

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

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.10+ installed
- Node.js & Bright Data CLI (`bdata`):
  ```bash
  npm install -g @brightdata/bdata-cli
  ```

### 2. Installation
Clone the repository and install Python dependencies:
```bash
git clone https://github.com/your-username/Web-Scraper-Self-Healing.git
cd Web-Scraper-Self-Healing
pip install -r requirements.txt
```

### 3. Environment Setup
Copy `.env.example` to `.env` and fill in your details:
```bash
cp .env.example .env
```
Edit `.env`:
```env
BRIGHTDATA_COLLECTOR_ID=your_collector_id_here
TARGET_URL=https://duckdb.org/docs/
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## 🏃 Running the Pipeline

### ⚡ 1-Click All-in-One Initiation (Recommended)
Automate all setup, self-healing scraper runs, ChromaDB indexing, and start the chatbot web server with **a single command**:

```bash
python start.py
```
*(On Windows CMD / PowerShell, you can also run `.\run.bat` or `.\run.ps1`)*

This script automatically:
1. Verifies `.env` environment variables.
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

## 🎭 How to Demo the Self-Heal Feature

For your hackathon presentation, you can demonstrate the automatic detection and self-healing loop in two ways:

### Method A: Interactive UI Demo (1-Click)
1. Open `http://localhost:8000` in your browser.
2. Click the **"🩹 Break & Self-Heal"** button on the left panel.
3. Watch the terminal console log:
   - Scraper returns broken/empty data.
   - `health_check.py` flags **DOM Selector Failure**.
   - `heal_loop.py` invokes `bdata scraper heal <COLLECTOR_ID> "<reason>"`.
   - Bright Data AI retrains selector model.
   - `bdata scraper approve <COLLECTOR_ID>` approves new schema.
   - Scraper re-runs, passes health check, and updates ChromaDB!

### Method B: Terminal CLI Demo
Run the orchestrator with the `--mock-unhealthy` flag:
```bash
python scripts/heal_loop.py --mock-unhealthy
```

You will see:
```text
--- 🔄 ATTEMPT 1 / 3 ---
🚨 HEALTH CHECK FAILED: DOM selector failure: 1 of 1 pages (100%) have empty or missing content fields.

🩹 TRIGGERING SELF-HEALING (Attempt 1)...
  -> bdata scraper heal c_sample_collector_12345 "DOM selector failure: 1 of 1 pages (100%) have empty content fields."
  -> bdata scraper approve c_sample_collector_12345
  💡 Bright Data AI is re-learning DOM selectors & updating extraction schema...

--- 🔄 ATTEMPT 2 / 3 ---
✨ HEALTH CHECK PASSED: Scrape healthy: 4 pages validated cleanly.
✅ PIPELINE HEALTHY: Updating baseline dataset & triggering vector store indexing...
```

---

## ⚙️ Automated GitHub Actions Workflow

The pipeline runs automatically on schedule via `.github/workflows/scrape-and-heal.yml`:
- **Schedule**: Every 6 hours (`0 */6 * * *`)
- **Manual Trigger**: Via GitHub Actions `workflow_dispatch` button
- **Auto-Commit**: Automatically commits updated baseline JSON data when health checks pass.

---

## 📄 License
MIT License.
