"""
app.py
------
Streamlit dashboard for U.S. Department of Labor FY disclosure data.
Covers H-1B (LCA) and PERM filings filtered to the IT/Software industry.

Sidebar "mode" selector drives the entire main area — each mode is a
self-contained tool with its own inputs and explanation.

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
LCA_FILE  = DATA_DIR / "lca_it.parquet"
PERM_FILE = DATA_DIR / "perm_it.parquet"
META_FILE = DATA_DIR / "last_updated.json"

# ---------------------------------------------------------------------------
# Guard: missing data
# ---------------------------------------------------------------------------

for label, path in [("H-1B (LCA)", LCA_FILE), ("PERM", PERM_FILE)]:
    if not path.exists():
        st.error(
            f"**{label} data file not found.**\n\n"
            "Run the one-time setup:\n"
            "```bash\npython scripts/preprocess.py\n```"
        )
        st.stop()

# ---------------------------------------------------------------------------
# Data loading (cached per session)
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner="Loading data…")
def load_lca() -> pd.DataFrame:
    """Load the pre-processed LCA Parquet. Cached for the session."""
    return pd.read_parquet(LCA_FILE)


@st.cache_data(show_spinner="Loading data…")
def load_perm() -> pd.DataFrame:
    """Load the pre-processed PERM Parquet. Cached for the session."""
    return pd.read_parquet(PERM_FILE)


@st.cache_data
def load_meta() -> dict:
    """Load last_updated.json metadata."""
    if not META_FILE.exists():
        return {}
    return json.loads(META_FILE.read_text())


lca  = load_lca()
perm = load_perm()
meta = load_meta()


# ---------------------------------------------------------------------------
# Sidebar — mode selector + context-sensitive controls
# ---------------------------------------------------------------------------

st.sidebar.title("📊 DOL IT Labor Dashboard")
st.sidebar.caption("H-1B · PERM · IT/Software only")

MODES = {
    "🏠 About":                    "about",
    "🔍 Explore Data":             "explore",
    "⚖️ Compare Companies":        "compare",
    "⏱️ Processing Time":          "processing",
    "🏅 Sponsorship Rank":         "sponsorship",
    "🗺️ Salary by State":          "state_salary",
    "📊 Wage Level Breakdown":     "wage_levels",
}

mode_label = st.sidebar.radio("What do you want to do?", list(MODES.keys()), index=0)
mode = MODES[mode_label]

st.sidebar.markdown("---")

# ── Context-sensitive sidebar controls ───────────────────────────────────────

if mode == "explore":
    st.sidebar.subheader("Filters")

    dataset_choice = st.sidebar.radio("Dataset", ["H-1B (LCA)", "PERM (Green Card)"], index=0)
    df_raw = lca if "LCA" in dataset_choice else perm

    job_search = st.sidebar.text_input("🔍 Search job title",
                                        placeholder="e.g. architect, devops")

    new_hire_only = False
    remote_only   = False

    if "LCA" in dataset_choice:
        new_hire_only = st.sidebar.toggle(
            "New hires only",
            value=False,
            help="Filters to fresh job openings only — excludes visa renewals and transfers.",
        )
        remote_only = st.sidebar.toggle(
            "Remote jobs only",
            value=False,
            help="Detects remote roles from worksite address keywords in LCA filings.",
        )
    else:
        st.sidebar.caption("ℹ️ New hire & remote filters available on H-1B only.")

    all_states    = sorted(df_raw["Worksite State"].dropna().unique())
    state_sel     = st.sidebar.multiselect("Worksite State", all_states, placeholder="All states")
    employer_srch = st.sidebar.text_input("Employer contains",
                                           placeholder="e.g. Google, Infosys")

    valid_wages = df_raw["Annual Wage"].dropna()
    if len(valid_wages):
        w_min = int(valid_wages.quantile(0.01))
        w_max = int(valid_wages.max())
        wage_sel = st.sidebar.slider("Annual Wage ($)", w_min, w_max, (w_min, w_max),
                                      step=5_000, format="$%d")
    else:
        wage_sel = (0, 0); w_min = w_max = 0

    all_statuses = sorted(df_raw["Status"].dropna().unique())
    status_sel   = st.sidebar.multiselect("Case Status", all_statuses, placeholder="All")

elif mode == "compare":
    st.sidebar.subheader("Pick two companies")
    all_employers = sorted(
        set(lca["Employer"].dropna().unique()) | set(perm["Employer"].dropna().unique())
    )
    co1 = st.sidebar.selectbox("Company A", [""] + all_employers, index=0)
    co2 = st.sidebar.selectbox("Company B", [""] + all_employers, index=0)

elif mode == "processing":
    st.sidebar.subheader("Filters")
    pt_dataset = st.sidebar.radio("Dataset", ["H-1B (LCA)", "PERM (Green Card)"], index=1)
    pt_employer = st.sidebar.text_input("Employer contains (optional)",
                                         placeholder="e.g. Amazon")

elif mode == "state_salary":
    st.sidebar.subheader("Filters")
    ss_job = st.sidebar.text_input("🔍 Job title contains",
                                    placeholder="e.g. software engineer")
    ss_level = st.sidebar.multiselect(
        "Wage Level", ["I", "II", "III", "IV"], placeholder="All levels"
    )

elif mode == "wage_levels":
    st.sidebar.subheader("Filters")
    wl_employer = st.sidebar.text_input("Employer contains",
                                         placeholder="e.g. Google, TCS")
    wl_job = st.sidebar.text_input("Job title contains (optional)",
                                    placeholder="e.g. engineer")

st.sidebar.markdown("---")
st.sidebar.caption(
    "Source: [U.S. Dept. of Labor — OFLC]"
    "(https://www.dol.gov/agencies/eta/foreign-labor/performance)"
)

# ---------------------------------------------------------------------------
# Shared: data freshness banner
# ---------------------------------------------------------------------------


def freshness_banner(ds_key: str) -> None:
    """Render the data freshness info bar for a given dataset key."""
    ds_meta = meta.get(ds_key, {})
    if not ds_meta:
        return
    fy      = ds_meta.get("fiscal_year", "")
    quarter = ds_meta.get("quarter", "")
    ts      = meta.get("last_updated_utc", "")
    ts_str  = ""
    if ts:
        try:
            ts_str = datetime.fromisoformat(ts).strftime("%b %d, %Y %H:%M UTC")
        except ValueError:
            ts_str = ts
    st.info(
        f"**Data:** FY{fy} {quarter} &nbsp;|&nbsp; "
        f"**Last updated:** {ts_str} &nbsp;|&nbsp; "
        f"**Total IT rows:** {ds_meta.get('rows', 0):,}"
    )


# ===========================================================================
# MODE: ABOUT
# ===========================================================================

if mode == "about":
    st.title("📊 DOL IT/Software Labor Dashboard")
    st.markdown("""
### Why this exists

Most job seekers negotiate salary blind, don't know which companies actively
sponsor visas, or waste time applying to employers who don't hire for their
background. But U.S. law requires companies to publicly disclose every H-1B
filing and green card application — including the **exact salary offered**.

This dashboard makes that data searchable and useful for anyone in IT/Software.

---

### What each tool does

| Tool | What it answers |
|------|----------------|
| 🔍 **Explore Data** | Browse all filings — filter by employer, role, state, salary, remote |
| ⚖️ **Compare Companies** | Side-by-side: wages, green card history, roles, states for any two employers |
| ⏱️ **Processing Time** | How long does DOL take to approve? By company, role, quarter |
| 🏅 **Sponsorship Rank** | Which companies sponsor the most green cards in IT? |
| 🗺️ **Salary by State** | Same role — what does it pay in CA vs TX vs NY? |
| 📊 **Wage Level Breakdown** | Does a company hire junior (Level I) or senior (Level IV) talent? |

---

### Understanding the data

**H-1B (LCA)** — Labor Condition Application. Filed before every H-1B petition.
The wage shown is the *legally committed* salary — the most reliable number available.

**PERM (Green Card)** — Filed when a company wants to sponsor permanent residency.
PERM filings = green card sponsorship. Filter to these to find visa-friendly employers.

**Wage Levels:**
| Level | Meaning |
|-------|---------|
| I | Entry-level, limited experience |
| II | Experienced, some independent judgement |
| III | Fully competent, independent contributor |
| IV | Expert, senior, lead, or supervisory |

**New hire filter** — LCA filings include a flag for whether it's a new hire vs
a visa renewal or transfer. Turn on "New hires only" to see fresh open roles.

**Remote detection** — Employers filing for remote workers write the home address
in the worksite field. We detect keywords like "home office", "WFH", "remote
work location" to surface these.

---

### Data freshness

Updated automatically every quarter via GitHub Actions from the OFLC
performance data page. The current quarter is shown at the top of each tool.

**Source code:** [github.com/anujg21/dol-labor-dashboard](https://github.com/anujg21/dol-labor-dashboard)

**Inspired by:** [this Instagram reel](https://www.instagram.com/reel/DWb1LvQk7JX/)
""")


# ===========================================================================
# MODE: EXPLORE DATA
# ===========================================================================

elif mode == "explore":
    ds_key = "lca" if "LCA" in dataset_choice else "perm"
    st.title(f"🔍 Explore Data — {dataset_choice}")
    freshness_banner(ds_key)

    # Apply filters
    df = df_raw.copy()
    if job_search.strip():
        df = df[df["Job Title"].str.contains(job_search.strip(), case=False, na=False)]
    if new_hire_only and "New Employment" in df.columns:
        df = df[df["New Employment"] == 1]
    if remote_only and "Is Remote" in df.columns:
        df = df[df["Is Remote"]]
    if state_sel:
        df = df[df["Worksite State"].isin(state_sel)]
    if employer_srch.strip():
        df = df[df["Employer"].str.contains(employer_srch.strip(), case=False, na=False)]
    if len(valid_wages) and (wage_sel[0] > w_min or wage_sel[1] < w_max):
        df = df[df["Annual Wage"].isna() |
                ((df["Annual Wage"] >= wage_sel[0]) & (df["Annual Wage"] <= wage_sel[1]))]
    if status_sel:
        df = df[df["Status"].isin(status_sel)]

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cases (filtered)", f"{len(df):,}")
    k2.metric("Unique Employers",  f"{df['Employer'].nunique():,}")
    w = df["Annual Wage"].dropna()
    if len(w):
        k3.metric("Median Wage", f"${w.median():,.0f}")
        k4.metric("Avg Wage",    f"${w.mean():,.0f}")

    st.markdown("---")

    tab_table, tab_charts, tab_employers = st.tabs(
        ["📋 Data Table", "📈 Charts", "🏆 Top Employers"]
    )

    DISPLAY_COLS = [c for c in [
        "Case #", "Status", "Employer", "Worksite State", "Is Remote", "New Employment",
        "Job Title", "SOC Code", "SOC Title", "Annual Wage", "Wage Level", "Decision Date",
    ] if c in df.columns]

    with tab_table:
        MAX = 10_000
        if len(df) > MAX:
            st.info(f"Showing first {MAX:,} of {len(df):,} rows. Download below for full set.")
        st.dataframe(df[DISPLAY_COLS].head(MAX).reset_index(drop=True),
                     use_container_width=True, height=520)
        st.download_button("⬇ Download full filtered CSV",
                           df.to_csv(index=False).encode("utf-8"),
                           file_name=f"{ds_key}_filtered.csv", mime="text/csv")

    with tab_charts:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Case Status")
            sc = df["Status"].value_counts().rename_axis("Status").reset_index(name="Count")
            st.bar_chart(sc.set_index("Status"))
        with c2:
            st.subheader("Top 15 States")
            ws = (df["Worksite State"].value_counts().head(15)
                  .rename_axis("State").reset_index(name="Count"))
            st.bar_chart(ws.set_index("State"))
        if len(w) > 10:
            st.subheader("Wage Distribution")
            bins   = list(range(0, 2_000_001, 25_000))
            labels = [f"${b // 1_000}k" for b in bins[:-1]]
            dist   = (pd.cut(w, bins=bins, labels=labels, right=False)
                      .value_counts().sort_index()
                      .rename_axis("Range").reset_index(name="Count"))
            st.bar_chart(dist.set_index("Range"))
        if "SOC Title" in df.columns:
            st.subheader("Top 15 IT Roles")
            roles = (df["SOC Title"].value_counts().head(15)
                     .rename_axis("Role").reset_index(name="Count"))
            st.bar_chart(roles.set_index("Role"))

    with tab_employers:
        st.subheader("Top 50 Employers by Case Volume")
        top = (df.groupby("Employer")
               .agg(Cases=("Case #", "count"),
                    Median_Wage=("Annual Wage", "median"),
                    States=("Worksite State",
                            lambda x: ", ".join(sorted(x.dropna().unique()[:5]))))
               .sort_values("Cases", ascending=False).head(50).reset_index())
        top["Median_Wage"] = top["Median_Wage"].apply(
            lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
        )
        top.columns = ["Employer", "Cases", "Median Annual Wage", "States (sample)"]
        st.dataframe(top, use_container_width=True, height=520)


# ===========================================================================
# MODE: COMPARE COMPANIES
# ===========================================================================

elif mode == "compare":
    st.title("⚖️ Compare Two Companies")
    st.caption(
        "Side-by-side comparison of wages, green card history, roles, and states "
        "for any two employers — useful when deciding between two job offers."
    )
    freshness_banner("lca")

    if not co1 or not co2:
        st.info("👈 Select two companies from the sidebar to begin.")
        st.stop()

    if co1 == co2:
        st.warning("Please select two different companies.")
        st.stop()

    def company_stats(name: str) -> dict:
        l = lca[lca["Employer"] == name]
        p = perm[perm["Employer"] == name]
        w = l["Annual Wage"].dropna()
        roles = l["SOC Title"].value_counts().head(5).index.tolist()
        states = sorted((set(l["Worksite State"].dropna().unique()) |
                         set(p["Worksite State"].dropna().unique())))
        levels = l["Wage Level"].value_counts().to_dict() if "Wage Level" in l.columns else {}
        return {
            "lca_cases":    len(l),
            "perm_cases":   len(p),
            "sponsors_gc":  len(p) > 0,
            "median_wage":  w.median() if len(w) else None,
            "avg_wage":     w.mean()   if len(w) else None,
            "top_roles":    roles,
            "states":       states[:8],
            "wage_levels":  levels,
            "remote_count": int(l["Is Remote"].sum()) if "Is Remote" in l.columns else 0,
        }

    s1, s2 = company_stats(co1), company_stats(co2)

    # KPI comparison
    col1, col_mid, col2 = st.columns([5, 1, 5])

    def _fmt_wage(v):
        return f"${v:,.0f}" if v is not None and pd.notna(v) else "—"

    def _kpi(col, label, v1, v2, fmt=str):
        col.markdown(f"**{label}**")
        a, b = st.columns(2)
        a.metric(co1[:20], fmt(v1))
        b.metric(co2[:20], fmt(v2))

    with col1:
        st.subheader(co1)
        st.metric("H-1B Filings",    f"{s1['lca_cases']:,}")
        st.metric("PERM Filings",    f"{s1['perm_cases']:,}")
        st.metric("Sponsors Green Card", "✅ Yes" if s1["sponsors_gc"] else "❌ No")
        st.metric("Median Annual Wage",  _fmt_wage(s1["median_wage"]))
        st.metric("Remote Filings",  f"{s1['remote_count']:,}")
        st.markdown("**Top roles:**")
        for r in s1["top_roles"]:
            st.markdown(f"- {r}")
        st.markdown("**States:** " + ", ".join(s1["states"]) if s1["states"] else "—")

    with col_mid:
        st.markdown("<div style='text-align:center;font-size:2rem;padding-top:3rem'>vs</div>",
                    unsafe_allow_html=True)

    with col2:
        st.subheader(co2)
        st.metric("H-1B Filings",    f"{s2['lca_cases']:,}")
        st.metric("PERM Filings",    f"{s2['perm_cases']:,}")
        st.metric("Sponsors Green Card", "✅ Yes" if s2["sponsors_gc"] else "❌ No")
        st.metric("Median Annual Wage",  _fmt_wage(s2["median_wage"]))
        st.metric("Remote Filings",  f"{s2['remote_count']:,}")
        st.markdown("**Top roles:**")
        for r in s2["top_roles"]:
            st.markdown(f"- {r}")
        st.markdown("**States:** " + ", ".join(s2["states"]) if s2["states"] else "—")

    # Wage level comparison
    if s1["wage_levels"] or s2["wage_levels"]:
        st.markdown("---")
        st.subheader("Wage Level Distribution")
        all_levels = sorted(set(s1["wage_levels"]) | set(s2["wage_levels"]))
        wl_df = pd.DataFrame({
            co1[:30]: [s1["wage_levels"].get(l, 0) for l in all_levels],
            co2[:30]: [s2["wage_levels"].get(l, 0) for l in all_levels],
        }, index=all_levels)
        st.bar_chart(wl_df)
        st.caption("Level I = junior · Level IV = senior/lead")


# ===========================================================================
# MODE: PROCESSING TIME
# ===========================================================================

elif mode == "processing":
    st.title("⏱️ Processing Time Tracker")
    st.caption(
        "How long does the DOL take to approve H-1B and PERM cases? "
        "Useful for planning your visa timeline — by company or overall."
    )

    df_pt = (lca if "LCA" in pt_dataset else perm).copy()
    freshness_banner("lca" if "LCA" in pt_dataset else "perm")

    if "Received Date" not in df_pt.columns or "Decision Date" not in df_pt.columns:
        st.error("Received Date or Decision Date not found in the data.")
        st.stop()

    df_pt["Received Date"]  = pd.to_datetime(df_pt["Received Date"],  errors="coerce")
    df_pt["Decision Date"]  = pd.to_datetime(df_pt["Decision Date"],  errors="coerce")
    df_pt["Processing Days"] = (df_pt["Decision Date"] - df_pt["Received Date"]).dt.days
    df_pt = df_pt[(df_pt["Processing Days"] > 0) & (df_pt["Processing Days"] < 1000)]

    if pt_employer.strip():
        df_pt = df_pt[df_pt["Employer"].str.contains(pt_employer.strip(), case=False, na=False)]

    if df_pt.empty:
        st.warning("No data for these filters.")
        st.stop()

    pd_ = df_pt["Processing Days"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cases analysed", f"{len(df_pt):,}")
    k2.metric("Median days",    f"{pd_.median():.0f}")
    k3.metric("Avg days",       f"{pd_.mean():.0f}")
    k4.metric("90th pct",       f"{pd_.quantile(0.9):.0f}")

    st.markdown("---")
    ta, tb = st.tabs(["📊 Distribution", "🏢 By Employer"])

    with ta:
        st.subheader("Processing Time Distribution")
        bins   = list(range(0, 501, 10))
        labels = [f"{b}d" for b in bins[:-1]]
        dist   = (pd.cut(pd_, bins=bins, labels=labels, right=False)
                  .value_counts().sort_index()
                  .rename_axis("Days").reset_index(name="Cases"))
        st.bar_chart(dist.set_index("Days"))

    with tb:
        st.subheader("Median Processing Days by Employer (top 30)")
        emp_pt = (df_pt.groupby("Employer")["Processing Days"]
                  .agg(["median", "mean", "count"])
                  .query("count >= 5")
                  .sort_values("median")
                  .head(30)
                  .reset_index())
        emp_pt.columns = ["Employer", "Median Days", "Avg Days", "Cases"]
        emp_pt["Median Days"] = emp_pt["Median Days"].round(0).astype(int)
        emp_pt["Avg Days"]    = emp_pt["Avg Days"].round(0).astype(int)
        st.dataframe(emp_pt, use_container_width=True, height=500)
        st.caption("Only employers with ≥ 5 cases shown for statistical reliability.")


# ===========================================================================
# MODE: SPONSORSHIP RANK
# ===========================================================================

elif mode == "sponsorship":
    st.title("🏅 Green Card Sponsorship Rank")
    st.caption(
        "Ranks IT employers by number of PERM (green card) filings. "
        "More filings = more actively sponsoring. Use this to find employers "
        "who are willing to sponsor your green card."
    )
    freshness_banner("perm")

    rank = (perm.groupby("Employer")
            .agg(
                PERM_Filings  =("Case #",        "count"),
                Certified     =("Status",         lambda x: (x == "Certified").sum()),
                Median_Wage   =("Annual Wage",    "median"),
                Top_Roles     =("SOC Title",      lambda x: x.value_counts().index[0]
                                if len(x) else "—"),
                States        =("Worksite State", lambda x: ", ".join(
                                sorted(x.dropna().unique()[:4]))),
            )
            .sort_values("PERM_Filings", ascending=False)
            .reset_index())

    rank["Cert Rate"]    = (rank["Certified"] / rank["PERM_Filings"] * 100).round(1).astype(str) + "%"
    rank["Median_Wage"]  = rank["Median_Wage"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "—")
    rank = rank.drop(columns=["Certified"])
    rank.columns = ["Employer", "PERM Filings", "Median Wage",
                    "Top Role", "States", "Cert Rate"]

    # KPIs
    k1, k2, k3 = st.columns(3)
    k1.metric("Companies sponsoring",   f"{len(rank):,}")
    k2.metric("Total PERM filings",     f"{len(perm):,}")
    k3.metric("Certified rate (all)",
              f"{(perm['Status'] == 'Certified').mean() * 100:.1f}%")

    st.markdown("---")

    search = st.text_input("🔍 Filter by employer name", placeholder="e.g. Amazon, Wipro")
    if search.strip():
        rank = rank[rank["Employer"].str.contains(search.strip(), case=False, na=False)]

    st.dataframe(rank, use_container_width=True, height=580)
    st.caption(
        "**Cert Rate** = % of filings approved. High rate + high volume = "
        "employer experienced with sponsorship process."
    )


# ===========================================================================
# MODE: SALARY BY STATE
# ===========================================================================

elif mode == "state_salary":
    st.title("🗺️ Salary by State")
    st.caption(
        "Compare what the same role pays across different U.S. states — "
        "based on actual wages filed with the DOL, not survey estimates."
    )
    freshness_banner("lca")

    df_ss = lca.copy()
    if ss_job.strip():
        df_ss = df_ss[df_ss["Job Title"].str.contains(ss_job.strip(), case=False, na=False)]
    if ss_level:
        df_ss = df_ss[df_ss["Wage Level"].isin(ss_level)]

    if df_ss.empty:
        st.warning("No results — try a broader job title search.")
        st.stop()

    if not ss_job.strip():
        st.info("👈 Enter a job title in the sidebar to see salary by state. "
                "Example: `software engineer`, `data scientist`, `architect`")

    by_state = (df_ss.groupby("Worksite State")["Annual Wage"]
                .agg(["count", "median", "mean",
                      lambda x: x.quantile(0.25),
                      lambda x: x.quantile(0.75)])
                .reset_index())
    by_state.columns = ["State", "Cases", "Median", "Avg", "P25", "P75"]
    by_state = by_state[by_state["Cases"] >= 5].sort_values("Median", ascending=False)

    k1, k2 = st.columns(2)
    k1.metric("States with data", f"{len(by_state):,}")
    k2.metric("Total cases",      f"{by_state['Cases'].sum():,}")

    st.markdown("---")
    tab_chart, tab_table = st.tabs(["📊 Chart", "📋 Table"])

    with tab_chart:
        st.subheader("Median Annual Wage by State")
        chart_data = by_state.set_index("State")[["Median"]].head(25)
        st.bar_chart(chart_data)
        st.caption("Top 25 states by median wage. Min 5 cases per state.")

    with tab_table:
        display = by_state.copy()
        for col in ["Median", "Avg", "P25", "P75"]:
            display[col] = display[col].apply(
                lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
            )
        display.columns = ["State", "Cases", "Median Wage", "Avg Wage", "P25", "P75"]
        st.dataframe(display, use_container_width=True, height=550)
        st.caption("P25 / P75 = 25th and 75th percentile wages.")


# ===========================================================================
# MODE: WAGE LEVEL BREAKDOWN
# ===========================================================================

elif mode == "wage_levels":
    st.title("📊 Wage Level Breakdown")
    st.caption(
        "See whether a company files mostly junior (Level I) or senior (Level IV) roles. "
        "A company advertising 'Senior Engineer' but filing Level I wages is a red flag."
    )
    freshness_banner("lca")

    df_wl = lca.copy()
    if wl_employer.strip():
        df_wl = df_wl[df_wl["Employer"].str.contains(wl_employer.strip(), case=False, na=False)]
    if wl_job.strip():
        df_wl = df_wl[df_wl["Job Title"].str.contains(wl_job.strip(), case=False, na=False)]

    if df_wl.empty:
        st.warning("No results for these filters.")
        st.stop()

    if not wl_employer.strip():
        st.info("👈 Enter an employer name in the sidebar to see their wage level profile. "
                "Or leave blank to see the industry-wide breakdown.")

    # Overall breakdown
    wl_counts = (df_wl.groupby(["Wage Level"])
                 .agg(Cases=("Case #", "count"),
                      Median_Wage=("Annual Wage", "median"))
                 .reset_index()
                 .sort_values("Wage Level"))
    wl_counts["Median_Wage"] = wl_counts["Median_Wage"].apply(
        lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Filings by Wage Level")
        st.bar_chart(wl_counts.set_index("Wage Level")["Cases"])
        st.caption("Level I = entry · Level IV = senior/lead")
    with col2:
        st.subheader("Median Wage by Level")
        st.dataframe(wl_counts.rename(columns={
            "Wage Level": "Level", "Cases": "Filings", "Median_Wage": "Median Wage"
        }), use_container_width=True)

    # Per-employer breakdown (top 20)
    st.markdown("---")
    st.subheader("Level Mix by Employer (top 20 by volume)")
    pivot = (df_wl.groupby(["Employer", "Wage Level"])
             .size().unstack(fill_value=0)
             .assign(Total=lambda d: d.sum(axis=1))
             .sort_values("Total", ascending=False)
             .drop(columns="Total")
             .head(20))
    st.bar_chart(pivot)
    st.caption(
        "Each bar segment = number of filings at that wage level. "
        "A company with mostly Level I/II filings pays more junior-level salaries."
    )
