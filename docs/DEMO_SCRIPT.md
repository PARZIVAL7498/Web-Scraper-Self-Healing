# Demo script (90 seconds) — Into the Scrape-Verse

Pinned collector (same ID everywhere): `c_mt2z0drp1irsde3ydk`  
Studio: https://brightdata.com/cp/scrapers/c_mt2z0drp1irsde3ydk  
Proof: `docs/proof_self_heal_transcript.txt`, `data/proof_bdata_run.json`

## Setup (once)

```bash
npm i -g @brightdata/cli
bdata login --api-key $BRIGHTDATA_API_KEY
# .env: BRIGHTDATA_COLLECTOR_ID + OPENROUTER_API_KEY + SCRAPE_ALLOW_FALLBACK=0
pip install -r requirements.txt
python -m uvicorn chatbot.app:app --host 127.0.0.1 --port 8000
```

## Shot list (VO + screen)

| t | Screen | Say |
|---|--------|-----|
| 0–10s | UI sidebar: brand + collector id | “Docs scrapers die when the DOM moves. We health-check empty extracts.” |
| 10–25s | Click **Break & self-heal** | “Demo break injects empty content. Timeline: Scrape → Health FAIL.” |
| 25–55s | Timeline advances to Heal; terminal/`heal-log` shows `bdata scraper heal` | “Real `bdata scraper heal` on the same `c_*`. Then Studio re-run.” |
| 55–75s | Timeline Index → done; status shows engine `bdata_cli` | “PASS, re-index Chroma. Proof artifact matches this collector.” |
| 75–90s | RAG tab: ask one docs question; show citations | “OpenRouter answers from healed scrape with citations.” |

## Camera checklist

1. Same `c_mt2z0drp1irsde3ydk` on UI, terminal, and Bright Data CP tab.
2. Heal panel labels: empty extract = demo trigger; heal CLI = real.
3. Do not paste API keys on camera.
4. If heal is slow, cut to pre-recorded `docs/proof_self_heal_transcript.txt` then return to live chat.

## LinkedIn (Daily Bugle)

Post the 90s clip. Tag **WeMakeDevs**. Mention Scraper Studio collector `c_mt2z0drp1irsde3ydk`. Draft: `docs/LINKEDIN_POST.md`.
