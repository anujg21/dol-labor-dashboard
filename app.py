"""
app.py
------
Streamlit dashboard for U.S. Department of Labor FY disclosure data.
Covers H-1B (LCA) and PERM filings filtered to the IT/Software industry.

Data is pre-processed to Parquet by scripts/preprocess.py and updated
automatically each quarter via GitHub Actions.

Run locally:
    streamlit run app.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DOL IT/Software Labor Dashboard",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
PARQUET_FILES = {
    "H-1B (LCA)":       DATA_DIR / "lca_it.parquet",
    "PERM (Green Card)": DATA_DIR / "perm_it.parquet",
}
METADATA_FILE = DATA_DIR / "last_updated.json"

# ---------------------------------------------------------------------------
# Guard: missing data
# ---------------------------------------------------------------------------

missing = [name for name, p in PARQUET_FILES.items() if not p.exists()]
if missing:
    st.error(
        "**Parquet data files not found.**\n\n"
        "Run the one-time setup:\n"
        "```bash\n"
        "# 1. Place Excel files in data/raw/\n"
        "# 2. Run:\n"
        "python scripts/preprocess.py\n"
        "```\n\n"
        f"Missing datasets: {', '.join(missing)}"
    )
    st.stop()

# ---------------------------------------------------------------------------
# Data loading (cached per session)
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner="Loading data…")
def load_dataset(path: Path) -> pd.DataFrame:
    """Load a Parquet dataset. Cached for the lifetime of the Streamlit session."""
    return pd.read_parquet(path)


@st.cache_data
def load_metadata() -> dict:
    """Load the last_updated.json metadata file."""
    if not METADATA_FILE.exists():
        return {}
    return json.loads(METADATA_FILE.read_text())


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("📊 DOL IT Labor Dashboard")
st.sidebar.caption("H-1B · PERM · IT/Software industry only")

# Dataset selector
dataset_choice = st.sidebar.radio("Dataset", list(PARQUET_FILES.keys()), index=0)
df_raw = load_dataset(PARQUET_FILES[dataset_choice])
meta = load_metadata()

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")

# Job title search — top of filters (most common use case)
job_search = st.sidebar.text_input(
    "🔍 Search job title",
    placeholder="e.g. architect, data scientist, devops",
)

# Remote toggle (LCA only — PERM form does not expose worksite address)
if dataset_choice == "H-1B (LCA)":
    remote_only = st.sidebar.toggle(
        "Remote jobs only",
        value=False,
        help=(
            "Detects remote roles from free-text worksite address in LCA forms "
            "(keywords: remote, home office, WFH, telecommute, etc.)."
        ),
    )
else:
    remote_only = False
    st.sidebar.caption("ℹ️ Remote filter available on H-1B (LCA) only.")

st.sidebar.markdown("---")

# Worksite state
all_states = sorted(df_raw["Worksite State"].dropna().unique())
state_sel = st.sidebar.multiselect("Worksite State", all_states, placeholder="All states")

# Employer
employer_search = st.sidebar.text_input(
    "Employer name contains", placeholder="e.g. Google, Infosys, Amazon"
)

# Annual wage slider
valid_wages = df_raw["Annual Wage"].dropna()
if len(valid_wages) > 0:
    w_min = int(valid_wages.quantile(0.01))
    w_max = int(valid_wages.max())
    wage_sel = st.sidebar.slider(
        "Annual Wage ($)", w_min, w_max, (w_min, w_max), step=5_000, format="$%d"
    )
else:
    wage_sel = (0, 0)
    w_min = w_max = 0

# Case status
all_statuses = sorted(df_raw["Status"].dropna().unique())
status_sel = st.sidebar.multiselect("Case Status", all_statuses, placeholder="All statuses")

st.sidebar.markdown("---")
st.sidebar.caption("Source: [U.S. Dept. of Labor — OFLC](https://www.dol.gov/agencies/eta/foreign-labor/performance)")

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------

df: pd.DataFrame = df_raw

if job_search.strip():
    df = df[df["Job Title"].str.contains(job_search.strip(), case=False, na=False)]

if remote_only and "Is Remote" in df.columns:
    df = df[df["Is Remote"]]

if state_sel:
    df = df[df["Worksite State"].isin(state_sel)]

if employer_search.strip():
    df = df[df["Employer"].str.contains(employer_search.strip(), case=False, na=False)]

if len(valid_wages) > 0 and (wage_sel[0] > w_min or wage_sel[1] < w_max):
    df = df[
        df["Annual Wage"].isna()
        | ((df["Annual Wage"] >= wage_sel[0]) & (df["Annual Wage"] <= wage_sel[1]))
    ]

if status_sel:
    df = df[df["Status"].isin(status_sel)]

# ---------------------------------------------------------------------------
# Header + last-updated banner
# ---------------------------------------------------------------------------

st.title(f"DOL IT/Software Labor Dashboard — {dataset_choice}")

# Show data freshness
ds_key = "lca" if "LCA" in dataset_choice else "perm"
ds_meta = meta.get(ds_key, {})
if ds_meta:
    fy = ds_meta.get("fiscal_year", "")
    quarter = ds_meta.get("quarter", "")
    updated_utc = meta.get("last_updated_utc", "")
    updated_str = ""
    if updated_utc:
        try:
            dt = datetime.fromisoformat(updated_utc)
            updated_str = dt.strftime("%B %d, %Y %H:%M UTC")
        except ValueError:
            updated_str = updated_utc

    st.info(
        f"**Data:** FY{fy} {quarter} &nbsp;|&nbsp; "
        f"**Last updated:** {updated_str} &nbsp;|&nbsp; "
        f"**Total IT rows:** {ds_meta.get('rows', 0):,}"
    )

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------

k1, k2, k3, k4 = st.columns(4)
k1.metric("Cases (filtered)", f"{len(df):,}")
k2.metric("Unique Employers", f"{df['Employer'].nunique():,}")
w = df["Annual Wage"].dropna()
if len(w):
    k3.metric("Median Annual Wage", f"${w.median():,.0f}")
    k4.metric("Avg Annual Wage",    f"${w.mean():,.0f}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_data, tab_analytics, tab_employers = st.tabs(
    ["📋 Data Table", "📈 Analytics", "🏆 Top Employers"]
)

DISPLAY_COLS = [
    c for c in [
        "Case #", "Status", "Employer", "Worksite State", "Is Remote",
        "Job Title", "SOC Code", "SOC Title", "Annual Wage", "Wage Level",
        "Decision Date", "Fiscal Year", "Quarter",
    ]
    if c in df.columns
]

# ── Tab 1: Data Table ────────────────────────────────────────────────────────

with tab_data:
    MAX_DISPLAY = 10_000
    total = len(df)

    if total > MAX_DISPLAY:
        st.info(
            f"Showing first **{MAX_DISPLAY:,}** of **{total:,}** matching rows. "
            "Download the full filtered set below."
        )

    st.dataframe(
        df[DISPLAY_COLS].head(MAX_DISPLAY).reset_index(drop=True),
        use_container_width=True,
        height=520,
    )

    st.download_button(
        label="⬇ Download full filtered data (CSV)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"{ds_key}_it_filtered.csv",
        mime="text/csv",
    )

# ── Tab 2: Analytics ─────────────────────────────────────────────────────────

with tab_analytics:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Case Status")
        status_counts = (
            df["Status"].value_counts()
            .rename_axis("Status").reset_index(name="Count")
        )
        st.bar_chart(status_counts.set_index("Status"))

    with col2:
        st.subheader("Top 15 Worksite States")
        state_counts = (
            df["Worksite State"].value_counts().head(15)
            .rename_axis("State").reset_index(name="Count")
        )
        st.bar_chart(state_counts.set_index("State"))

    if len(w) > 10:
        st.subheader("Wage Distribution (Annual)")
        bins   = list(range(0, 2_000_001, 25_000))
        labels = [f"${b // 1_000}k" for b in bins[:-1]]
        binned = pd.cut(w, bins=bins, labels=labels, right=False)
        dist   = (
            binned.value_counts().sort_index()
            .rename_axis("Range").reset_index(name="Count")
        )
        st.bar_chart(dist.set_index("Range"))

    if "SOC Title" in df.columns:
        st.subheader("Top 15 IT Roles (by SOC Title)")
        roles = (
            df["SOC Title"].value_counts().head(15)
            .rename_axis("Role").reset_index(name="Count")
        )
        st.bar_chart(roles.set_index("Role"))

# ── Tab 3: Top Employers ──────────────────────────────────────────────────────

with tab_employers:
    st.subheader("Top 50 Employers by Case Volume")

    top = (
        df.groupby("Employer")
        .agg(
            Cases       =("Case #",         "count"),
            Median_Wage =("Annual Wage",     "median"),
            States      =("Worksite State",  lambda x: ", ".join(sorted(x.dropna().unique()[:5]))),
        )
        .sort_values("Cases", ascending=False)
        .head(50)
        .reset_index()
    )
    top["Median_Wage"] = top["Median_Wage"].apply(
        lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
    )
    top.columns = ["Employer", "Cases", "Median Annual Wage", "States (sample)"]
    st.dataframe(top, use_container_width=True, height=520)
