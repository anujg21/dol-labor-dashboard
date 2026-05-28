"""
preprocess.py
-------------
Reads raw OFLC disclosure Excel files, filters to IT/software occupations,
annualises wages, flags remote roles, and writes compact Parquet files.

Outputs (written to data/):
    lca_it.parquet   — H-1B Labor Condition Application (IT rows only)
    perm_it.parquet  — PERM Permanent Labor Certification (IT rows only)
    last_updated.json — Metadata: quarter, row counts, timestamp

Usage:
    # Auto-detect files from data/raw/
    python scripts/preprocess.py

    # Explicit file paths
    python scripts/preprocess.py \
        --lca  data/raw/LCA_Disclosure_Data_FY2026_Q3.xlsx \
        --perm data/raw/PERM_Disclosure_Data_FY2026_Q3.xlsx

IT/Software filter:
    SOC 15-xxxx — Computer & Mathematical Occupations (core)
    SOC 11-3021 — Computer and Information Systems Managers
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"

# SOC codes considered IT/Software
IT_SOC_PREFIXES: tuple[str, ...] = ("15-",)
IT_SOC_EXACT: frozenset[str] = frozenset({"11-3021.00", "11-3021"})

# Wage unit → annual multiplier
WAGE_UNIT_MAP: dict[str, int] = {
    "Hour": 2080,
    "Week": 52,
    "Bi-Weekly": 26,
    "Month": 12,
    "Year": 1,
}

# Wages above this value are treated as data-entry errors and nulled out
MAX_PLAUSIBLE_ANNUAL_WAGE = 2_000_000

# Keywords that indicate a remote worksite in the LCA form's free-text field
REMOTE_PATTERN = re.compile(
    r"remote|home\s+office|telecommut|work\s+from\s+home|\bwfh\b|telework|beneficiary.{0,5}home",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Column selections (raw name -> display name)
# ---------------------------------------------------------------------------

LCA_COLUMNS: dict[str, str] = {
    "CASE_NUMBER":           "Case #",
    "CASE_STATUS":           "Status",
    "VISA_CLASS":            "Visa",
    "DECISION_DATE":         "Decision Date",
    "EMPLOYER_NAME":         "Employer",
    "EMPLOYER_STATE":        "Employer State",
    "WORKSITE_STATE":        "Worksite State",
    "WORKSITE_ADDRESS1":     "Worksite Address",
    "JOB_TITLE":             "Job Title",
    "SOC_CODE":              "SOC Code",
    "SOC_TITLE":             "SOC Title",
    "WAGE_RATE_OF_PAY_FROM": "Wage From",
    "WAGE_UNIT_OF_PAY":      "Wage Unit",
    "PREVAILING_WAGE":       "Prevailing Wage",
    "PW_WAGE_LEVEL":         "Wage Level",
    "FULL_TIME_POSITION":    "Full Time",
}

PERM_COLUMNS: dict[str, str] = {
    "CASE_NUMBER":              "Case #",
    "CASE_STATUS":              "Status",
    "DECISION_DATE":            "Decision Date",
    "EMP_BUSINESS_NAME":        "Employer",
    "EMP_STATE":                "Employer State",
    "PRIMARY_WORKSITE_STATE":   "Worksite State",
    "JOB_TITLE":                "Job Title",
    "PWD_SOC_CODE":             "SOC Code",
    "PWD_SOC_TITLE":            "SOC Title",
    "JOB_OPP_WAGE_FROM":        "Wage From",
    "JOB_OPP_WAGE_TO":          "Wage To",
    "JOB_OPP_WAGE_PER":         "Wage Unit",
    "OCCUPATION_TYPE":          "Occupation Type",
}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
    )


def is_it_soc(code: object) -> bool:
    """Return True if *code* belongs to an IT/Software SOC group."""
    if pd.isna(code):
        return False
    c = str(code).strip()
    return c.startswith(IT_SOC_PREFIXES) or c in IT_SOC_EXACT


def annualise_wages(df: pd.DataFrame, wage_col: str, unit_col: str) -> pd.DataFrame:
    """
    Add an ``Annual Wage`` column by multiplying *wage_col* by the
    unit multiplier from WAGE_UNIT_MAP.  Values above MAX_PLAUSIBLE_ANNUAL_WAGE
    are set to NaN (data-entry errors in the source).
    """
    df["Annual Wage"] = df.apply(
        lambda r: r[wage_col] * WAGE_UNIT_MAP.get(str(r[unit_col]), 1)
        if pd.notna(r[wage_col]) else None,
        axis=1,
    )
    mask = df["Annual Wage"] > MAX_PLAUSIBLE_ANNUAL_WAGE
    if mask.any():
        logger.debug("Nulling %d implausibly large wage entries.", mask.sum())
    df.loc[mask, "Annual Wage"] = None
    return df


def _latest_excel(pattern: str) -> Path | None:
    """Return the most recently modified file matching *pattern*, or None."""
    matches = sorted(glob.glob(str(RAW_DIR / pattern)), key=lambda p: Path(p).stat().st_mtime)
    return Path(matches[-1]) if matches else None


def _detect_quarter(path: Path) -> tuple[str, str]:
    """Extract (fiscal_year, quarter) from a DOL filename, e.g. FY2026_Q2."""
    m = re.search(r"FY(\d{4})_Q(\d)", path.name, re.IGNORECASE)
    if m:
        return m.group(1), f"Q{m.group(2)}"
    return "unknown", "unknown"


# ---------------------------------------------------------------------------
# Per-dataset processing
# ---------------------------------------------------------------------------


def process_lca(path: Path) -> tuple[pd.DataFrame, dict]:
    """
    Load, filter, and enrich an LCA disclosure Excel file.

    Returns:
        (dataframe, metadata_dict)
    """
    logger.info("Processing LCA: %s", path.name)
    df = pd.read_excel(path, usecols=list(LCA_COLUMNS.keys()), engine="openpyxl")
    df = df[df["SOC_CODE"].apply(is_it_soc)].copy()
    df = df.rename(columns=LCA_COLUMNS)

    df["Wage From"] = pd.to_numeric(df["Wage From"], errors="coerce")
    df = annualise_wages(df, "Wage From", "Wage Unit")

    # Detect remote worksites from free-text address field
    df["Worksite Address"] = df["Worksite Address"].astype(str)
    df["Is Remote"] = df["Worksite Address"].str.contains(REMOTE_PATTERN, na=False)

    df["Dataset"] = "LCA"
    fy, q = _detect_quarter(path)
    df["Fiscal Year"] = fy
    df["Quarter"] = q

    metadata = {
        "fiscal_year": fy,
        "quarter": q,
        "source_file": path.name,
        "rows": len(df),
        "remote_rows": int(df["Is Remote"].sum()),
    }
    logger.info("  → %d IT rows (%d remote)", metadata["rows"], metadata["remote_rows"])
    return df, metadata


def process_perm(path: Path) -> tuple[pd.DataFrame, dict]:
    """
    Load, filter, and enrich a PERM disclosure Excel file.

    Returns:
        (dataframe, metadata_dict)
    """
    logger.info("Processing PERM: %s", path.name)
    df = pd.read_excel(path, usecols=list(PERM_COLUMNS.keys()), engine="openpyxl")
    df = df[df["PWD_SOC_CODE"].apply(is_it_soc)].copy()
    df = df.rename(columns=PERM_COLUMNS)

    df["Wage From"] = pd.to_numeric(df["Wage From"], errors="coerce")
    df = annualise_wages(df, "Wage From", "Wage Unit")

    # PERM disclosure data does not include worksite address
    df["Is Remote"] = False

    df["Dataset"] = "PERM"
    fy, q = _detect_quarter(path)
    df["Fiscal Year"] = fy
    df["Quarter"] = q

    metadata = {
        "fiscal_year": fy,
        "quarter": q,
        "source_file": path.name,
        "rows": len(df),
        "remote_rows": 0,
    }
    logger.info("  → %d IT rows", metadata["rows"])
    return df, metadata


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(lca_path: Path, perm_path: Path) -> None:
    """Process both datasets and write output Parquet + metadata."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    lca_df, lca_meta = process_lca(lca_path)
    perm_df, perm_meta = process_perm(perm_path)

    # Write Parquet
    lca_out = DATA_DIR / "lca_it.parquet"
    perm_out = DATA_DIR / "perm_it.parquet"
    lca_df.to_parquet(lca_out, index=False)
    perm_df.to_parquet(perm_out, index=False)
    logger.info("Wrote %s (%.1f KB)", lca_out.name, lca_out.stat().st_size / 1024)
    logger.info("Wrote %s (%.1f KB)", perm_out.name, perm_out.stat().st_size / 1024)

    # Write metadata
    meta = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "lca": lca_meta,
        "perm": perm_meta,
    }
    meta_path = DATA_DIR / "last_updated.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    logger.info("Wrote %s", meta_path.name)
    print(f"\nDone.  LCA: {lca_meta['rows']:,} rows | PERM: {perm_meta['rows']:,} rows")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Preprocess DOL disclosure files to Parquet.")
    p.add_argument("--lca",  type=Path, default=None,
                   help="Path to LCA Excel file (auto-detected from data/raw/ if omitted)")
    p.add_argument("--perm", type=Path, default=None,
                   help="Path to PERM Excel file (auto-detected from data/raw/ if omitted)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    _setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    lca_path = args.lca or _latest_excel("LCA_*Disclosure_Data_*.xlsx")
    perm_path = args.perm or _latest_excel("PERM_Disclosure_Data_*.xlsx")

    missing = [name for name, p in [("LCA", lca_path), ("PERM", perm_path)] if p is None]
    if missing:
        logger.error("Could not find input files for: %s", ", ".join(missing))
        logger.error("Place Excel files in %s or pass --lca / --perm flags.", RAW_DIR)
        sys.exit(1)

    run(lca_path, perm_path)


if __name__ == "__main__":
    main()
