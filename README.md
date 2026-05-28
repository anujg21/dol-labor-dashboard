# DOL IT/Software Labor Dashboard

An interactive Streamlit dashboard exploring U.S. Department of Labor quarterly
disclosure data for the **IT/Software industry** — covering H-1B (LCA) and PERM
(Green Card) filings.

<!-- DATA_BADGE --> **Data:** FY2026 Q2 &nbsp;| **Updated:** 2026-05-28

---

## Live Dashboard

**[https://dol-labor-dashboard-szpjdvwd4hp8qevqnv3ebe.streamlit.app](https://dol-labor-dashboard-szpjdvwd4hp8qevqnv3ebe.streamlit.app)**

---

## What's in the data?

| Dataset | Form | Description |
|---------|------|-------------|
| **LCA** | ETA-9035 | H-1B / H-1B1 Labor Condition Applications |
| **PERM** | ETA-9089 | Permanent Labor Certification (Green Card) |

All rows are filtered to **IT/Software occupations** (SOC 15-xxxx Computer &
Mathematical + SOC 11-3021 IT Managers).

**Source:** [OFLC Performance Data](https://www.dol.gov/agencies/eta/foreign-labor/performance)
— published by the U.S. Department of Labor, Employment & Training Administration.

---

## Features

- Filter by job title, employer, state, salary range, case status
- Remote job detection on LCA data (worksite address keyword analysis)
- Wage distribution, top employers, case-status breakdown charts
- CSV export of any filtered view
- Auto-refreshes each quarter via GitHub Actions

---

## Data Update History

See [CHANGELOG.md](CHANGELOG.md) for a full history of data refreshes.

---

## Local Development

```bash
# 1. Clone
git clone https://github.com/anujg21/dol-labor-dashboard.git
cd dol-labor-dashboard

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download latest DOL Excel files
python scripts/fetch_dol_data.py --dest data/raw

# 4. Preprocess to Parquet (one-time, ~2 min)
python scripts/preprocess.py

# 5. Run the dashboard
streamlit run app.py
```

---

## Architecture

```
GitHub repo
├── app.py                         # Streamlit dashboard
├── scripts/
│   ├── fetch_dol_data.py          # Scrapes DOL page, downloads Excel files
│   └── preprocess.py              # Filters & converts Excel → Parquet
├── data/
│   ├── lca_it.parquet             # Pre-processed LCA data (~5 MB)
│   ├── perm_it.parquet            # Pre-processed PERM data (~1 MB)
│   └── last_updated.json          # Quarter & timestamp metadata
└── .github/workflows/
    └── update_data.yml            # Quarterly cron pipeline
```

**Automated pipeline (GitHub Actions):**

```
Cron (quarterly)
  → check DOL page for new quarter files
  → skip if already current
  → download Excel files
  → run preprocess.py
  → commit updated parquets + metadata
  → Streamlit Cloud auto-redeploys
```

---

## Adding a New Quarter Manually

If you need to force an update before the scheduled cron:

1. Go to **Actions → Quarterly Data Update → Run workflow** in GitHub UI, or:
2. Run locally:
   ```bash
   python scripts/fetch_dol_data.py --dest data/raw
   python scripts/preprocess.py
   git add data/ CHANGELOG.md
   git commit -m "data: update to FY2026 Q3"
   git push
   ```

---

## Inspiration

This project was inspired by an Instagram reel: [https://www.instagram.com/reel/DWb1LvQk7JX/](https://www.instagram.com/reel/DWb1LvQk7JX/)

---

## License

Data is sourced from the U.S. Department of Labor (public domain).
Dashboard code is MIT licensed.
