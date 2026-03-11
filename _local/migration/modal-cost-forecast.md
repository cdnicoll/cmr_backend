# Modal cost forecast (CMR workers)

Rough cost predictions for CMR’s Modal workers, with **ingest** as the main cost driver (~3 min/run). Uses [Modal’s pricing](https://modal.com/pricing) (per-second, CPU + memory).

---

## Worker config (from `modal_workers.py`)

| Worker | Image | CPU | Memory | Timeout | Schedule / trigger |
|--------|--------|-----|--------|---------|--------------------|
| **ingest_resource** | standard | 2 | 2048 MiB (2 GiB) | 10 min | Spawned per resource after scrape |
| **scrape_resource** | browser (Playwright) | 2 | 2048 MiB (2 GiB) | 5 min | Spawned per new resource from discovery |
| **run_discovery** | discovery (RSS/YouTube) | (default) | (default) | 10 min | Every 6 hours |
| **run_recovery_pipeline** | standard | (default) | (default) | 5 min | Every 2 hours |

Ingest is capped at **max_containers=10**; extra work is queued.

---

## Modal rates (CPU + memory only; no GPU on these workers)

- **CPU:** $0.0000131 per physical core per second  
- **Memory:** $0.00000222 per GiB per second  

Billing is **per second of actual run time**. Assumed **preemptible** (default); non‑preemptible would be ~3×. Region choice can add **1.25×–2.5×** to these base rates.

---

## Per-second cost for 2 CPU + 2 GiB (ingest & scrape)

- CPU: 2 × $0.0000131 = **$0.0000262/sec**  
- Memory: 2 × $0.00000222 = **$0.00000444/sec**  
- **Total:** **$0.00003064/sec** → **~$0.00184/min** (~$0.110/hour)

So:

- **1 ingest run @ 3 min** ≈ **$0.00551** (base)  
- **1 ingest run @ 3 min** @ 1.5× region ≈ **$0.00827**

---

## Monthly cost scenarios (base pricing)

Assume:

- **Ingest:** 3 min per resource (your average).
- **Scrape:** ~1.5 min per resource (placeholder; adjust if you have data).
- **Discovery:** ~5 min per run × 4 runs/day ≈ 20 min/day.
- **Recovery:** ~0.5 min per run × 12 runs/day ≈ 6 min/day.

Discovery and recovery use default CPU/memory; we approximate with the same 2-core, 2-GiB rate for a conservative upper bound (they’re likely lower).

| Resources/day | Ingest (3 min each) | Scrape (1.5 min each) | Discovery + recovery | **Total/day (base)** | **Total/month (base)** |
|---------------|---------------------|------------------------|----------------------|-----------------------|-------------------------|
| 10 | $0.165 | $0.083 | ~$0.05 | **~$0.30** | **~$9** |
| 50 | $0.83 | $0.41 | ~$0.05 | **~$1.29** | **~$39** |
| 100 | $1.65 | $0.83 | ~$0.05 | **~$2.53** | **~$76** |
| 200 | $3.31 | $1.65 | ~$0.05 | **~$5.01** | **~$150** |
| 500 | $8.27 | $4.13 | ~$0.05 | **~$12.45** | **~$374** |
| 1000 | $16.53 | $8.26 | ~$0.05 | **~$24.84** | **~$745** |

So at **~3 min per ingest**, cost scales almost linearly with **number of resources processed per day**; ingest dominates.

---

## With region multiplier (e.g. 1.5×)

If you use a region with a 1.5× multiplier, multiply the “Total/month (base)” column by **1.5** (e.g. 100 resources/day: ~$76 → **~$114/month**).

---

## Plan credits (Starter / Team)

- **Starter:** $30/month compute credit. At base pricing, that’s roughly **~400–500 ingest runs/month** (3 min each) before you pay over the credit.
- **Team:** $250/month + $100 compute credit. The $100 credit is another **~1,800–2,000 ingest runs** at 3 min each (base).

---

## Summary

- **Ingest at ~3 min/run** is the main cost; scrape is next; discovery and recovery are small.
- **Per-ingest (3 min):** ~**$0.0055** base, ~**$0.0083** at 1.5× region.
- For planning: **monthly cost (base) ≈ (resources/day × 30 × $0.0055) + (resources/day × 30 × scrape_min × $0.00184) + ~$1.50** for discovery/recovery. Simplify to **~$0.22 per resource per month** (ingest + scrape) if scrape ≈ 1.5 min.
- To refine: plug in real **resources/day** and **average scrape duration**; consider **region multiplier** if not using the default region.
