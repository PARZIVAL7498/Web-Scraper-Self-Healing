# Demo script (90 seconds) — Competitor Dashboard

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
| 0–12s | Compare tab: Vercel vs Railway | “Same category: deployment. We scrape both docs with Scraper Studio and put them on one dashboard.” |
| 12–35s | Run compare → chart + citations | “Side-by-side: what they document, coverage signals, exportable report.” |
| 35–55s | Ask the docs on one URL | “Then ask like an analyst. Answers cite the competitor’s own pages.” |
| 55–80s | Break & self-heal timeline | “When their DOM moves, we don’t rewrite selectors. Real `bdata scraper heal` on the same `c_*`.” |
| 80–90s | Index done + collector id | “Heal, re-index, keep watching. Self-healing RAG is the engine under the dashboard.” |

## Camera checklist

1. Same `c_mt2z0drp1irsde3ydk` on UI, terminal, and Bright Data CP tab.
2. Lead with **Live compare**, not chat.
3. Heal panel labels: empty extract = demo trigger; heal CLI = real.
4. Do not paste API keys on camera.
5. If heal is slow, cut to pre-recorded `docs/proof_self_heal_transcript.txt` then return to the compare report.

## LinkedIn (Daily Bugle)

Post the 90s clip. Tag **WeMakeDevs**. Mention Scraper Studio collector `c_mt2z0drp1irsde3ydk`. Draft: `docs/LINKEDIN_POST.md`.
