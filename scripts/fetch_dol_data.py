"""
fetch_dol_data.py
-----------------
Scrapes the OFLC Performance Data page and downloads the latest
LCA and PERM quarterly disclosure Excel files.

DOL source: https://www.dol.gov/agencies/eta/foreign-labor/performance

Usage:
    python scripts/fetch_dol_data.py --dest /tmp/dol_raw
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERFORMANCE_PAGE = "https://www.dol.gov/agencies/eta/foreign-labor/performance"
BASE_URL = "https://www.dol.gov"

# Regex patterns to identify the disclosure Excel files we care about
FILE_PATTERNS = {
    "lca": re.compile(
        r"LCA_Dis[lc]+losure_Data_FY(\d{4})_Q(\d)\.xlsx", re.IGNORECASE
    ),
    "perm": re.compile(
        r"PERM_Disclosure_Data_FY(\d{4})_Q(\d)\.xlsx", re.IGNORECASE
    ),
}

REQUEST_TIMEOUT = 120  # seconds
CHUNK_SIZE = 1024 * 1024  # 1 MB

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


def _fetch_page(url: str) -> str:
    """Fetch a URL and return the response text."""
    headers = {"User-Agent": "dol-labor-dashboard/1.0 (github.com/anujg21/dol-labor-dashboard)"}
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _find_latest_links(html: str) -> dict[str, dict]:
    """
    Parse the OFLC performance page and return the highest FY/Q link
    for each file type (lca, perm).

    Returns:
        {
            "lca":  {"url": "...", "fy": "2026", "quarter": "Q2", "filename": "..."},
            "perm": {"url": "...", "fy": "2026", "quarter": "Q2", "filename": "..."},
        }
    """
    soup = BeautifulSoup(html, "html.parser")
    results: dict[str, dict] = {}

    for tag in soup.find_all("a", href=True):
        href: str = tag["href"]
        filename = href.split("/")[-1]

        for dataset, pattern in FILE_PATTERNS.items():
            m = pattern.search(filename)
            if not m:
                continue

            fy, quarter = m.group(1), m.group(2)
            full_url = href if href.startswith("http") else BASE_URL + href

            existing = results.get(dataset)
            if existing is None or (fy, quarter) > (existing["fy"], existing["quarter"]):
                results[dataset] = {
                    "url": full_url,
                    "fy": fy,
                    "quarter": f"Q{quarter}",
                    "filename": filename,
                }

    return results


def _download_file(url: str, dest_path: Path) -> None:
    """Stream-download a file to *dest_path*, showing progress."""
    headers = {"User-Agent": "dol-labor-dashboard/1.0"}
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading %s -> %s", url, dest_path)
    with requests.get(url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {pct:5.1f}%  ({downloaded // 1_000_000} MB)", end="", flush=True)
    print()
    logger.info("Saved %s (%.1f MB)", dest_path.name, dest_path.stat().st_size / 1_000_000)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_latest_metadata() -> dict[str, dict]:
    """
    Return metadata for the latest available LCA and PERM files on DOL.

    Returns:
        dict keyed by "lca" / "perm", each containing url/fy/quarter/filename.

    Raises:
        RuntimeError: if the page cannot be fetched or no files are found.
    """
    logger.info("Fetching OFLC performance page: %s", PERFORMANCE_PAGE)
    html = _fetch_page(PERFORMANCE_PAGE)
    links = _find_latest_links(html)

    if not links:
        raise RuntimeError("No LCA/PERM files found on the OFLC performance page.")

    return links


def download_latest(dest_dir: Path) -> dict[str, Path]:
    """
    Download the latest LCA and PERM Excel files into *dest_dir*.

    Returns:
        dict mapping dataset name ("lca" / "perm") to the downloaded Path.
    """
    links = get_latest_metadata()
    downloaded: dict[str, Path] = {}

    for dataset, meta in links.items():
        dest = dest_dir / meta["filename"]
        if dest.exists():
            logger.info("Already downloaded: %s — skipping.", dest.name)
        else:
            _download_file(meta["url"], dest)
        downloaded[dataset] = dest

    return downloaded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download latest OFLC disclosure files.")
    p.add_argument("--dest", type=Path, default=Path("data/raw"),
                   help="Directory to save downloaded files (default: data/raw)")
    p.add_argument("--list-only", action="store_true",
                   help="Print available file URLs without downloading")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    _setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    links = get_latest_metadata()

    if args.list_only:
        print(json.dumps(links, indent=2))
        return

    paths = download_latest(args.dest)
    for dataset, path in paths.items():
        print(f"{dataset.upper()}: {path}")


if __name__ == "__main__":
    main()
