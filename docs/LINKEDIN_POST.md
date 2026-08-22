# LinkedIn post draft (Daily Bugle track)

Tag: WeMakeDevs  
Event: Into the Scrape-Verse / Bright Data

---

Built a competitor dashboard for the Bright Data hackathon.

Vercel vs Railway (same category: deployment). We scrape both docs with Scraper Studio, put them on one board, and show a cited side-by-side report.

Under the hood: self-healing RAG.
1. Competitor ships a new layout → extract comes back empty
2. `bdata scraper heal` on collector `c_mt2z0drp1irsde3ydk`
3. Re-run → embed → the dashboard keeps comparing

Stack: Bright Data Scraper Studio CLI + ChromaDB + FastAPI.

Repo + demo video in comments.

#WeMakeDevs #BrightData #ScrapeVerse #CompetitiveIntel

---

Attach: 20–40s screen recording of Vercel vs Railway compare, then optional heal recovery.
