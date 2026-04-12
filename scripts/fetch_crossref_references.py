import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Iterable

import requests


def doi_from_pdf_path(pdf_path: Path) -> str | None:
    stem = pdf_path.stem
    if not stem.startswith("10.") or "_" not in stem:
        return None
    prefix, suffix = stem.split("_", 1)
    return f"{prefix}/{suffix}"


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def make_headers(mailto: str | None) -> dict[str, str]:
    if mailto:
        return {"User-Agent": f"PaperKG-Final/1.0 (mailto:{mailto})"}
    return {"User-Agent": "PaperKG-Final/1.0"}


def doi_variants(doi: str) -> list[str]:
    variants = [doi]
    if "/" not in doi:
        return variants

    prefix, suffix = doi.split("/", 1)
    parts = suffix.split(".")
    if not parts:
        return variants

    tail = parts[-1]
    if tail.isdigit() and len(tail) > 1 and tail.startswith("0"):
        stripped_tail = str(int(tail))
        variant = prefix + "/" + ".".join(parts[:-1] + [stripped_tail])
        if variant not in variants:
            variants.append(variant)

    return variants


def fetch_work(doi: str, headers: dict[str, str], timeout: int, max_retries: int) -> tuple[str, int, dict | None, str | None]:
    last_error = None
    last_status = 0

    for candidate_doi in doi_variants(doi):
        url = f"https://api.crossref.org/works/{candidate_doi}"

        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=timeout)
                status = response.status_code
                last_status = status

                if status == 200:
                    return candidate_doi, status, response.json().get("message"), None

                if status in {404, 410}:
                    break

                if status == 429:
                    retry_after = response.headers.get("Retry-After")
                    sleep_seconds = float(retry_after) if retry_after and retry_after.isdigit() else (2.0 + attempt)
                    time.sleep(sleep_seconds)
                    continue

                last_error = f"HTTP {status}: {response.text[:300]}"
                time.sleep(1.0 + attempt)
            except Exception as exc:  # noqa: BLE001
                last_error = repr(exc)
                time.sleep(1.0 + attempt)

    return doi, last_status, None, last_error


def iter_pdf_paths(pdf_root: Path) -> Iterable[Path]:
    for year_dir in sorted((p for p in pdf_root.iterdir() if p.is_dir()), key=lambda p: p.name):
        for pdf_path in sorted(year_dir.glob("*.pdf"), key=lambda p: p.name):
            yield pdf_path


def build_reference_rows(citing: dict, message: dict) -> list[dict]:
    rows = []
    references = message.get("reference") or []
    for idx, ref in enumerate(references, start=1):
        rows.append(
            {
                "citing_official_year": citing["official_year"],
                "citing_query_doi": citing["query_doi"],
                "citing_resolved_doi": citing["resolved_doi"],
                "citing_title": citing["title"],
                "citing_pdf_path": str(citing["pdf_path"]),
                "reference_index": idx,
                "ref_doi": ref.get("DOI", ""),
                "ref_unstructured": ref.get("unstructured", ""),
                "ref_article_title": ref.get("article-title", ""),
                "ref_journal_title": ref.get("journal-title", ""),
                "ref_author": ref.get("author", ""),
                "ref_year": ref.get("year", ""),
                "ref_volume": ref.get("volume", ""),
                "ref_issue": ref.get("issue", ""),
                "ref_first_page": ref.get("first-page", ""),
                "ref_key": ref.get("key", ""),
                "ref_raw_json": json.dumps(ref, ensure_ascii=False),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf-root",
        default="data/jmr_2000_2025/pdfs",
        help="Root directory containing year-organized PDF files.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/jmr_2000_2025/crossref_references",
        help="Output directory for raw JSON and flattened CSV files.",
    )
    parser.add_argument("--mailto", default=None, help="Optional mailto for Crossref polite pool.")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for pilot runs.")
    args = parser.parse_args()

    pdf_root = Path(args.pdf_root)
    out_dir = Path(args.out_dir)
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    headers = make_headers(args.mailto)
    pdf_paths = list(iter_pdf_paths(pdf_root))
    if args.limit > 0:
        pdf_paths = pdf_paths[: args.limit]

    paper_rows: list[dict] = []
    reference_rows: list[dict] = []

    total = len(pdf_paths)
    for idx, pdf_path in enumerate(pdf_paths, start=1):
        doi = doi_from_pdf_path(pdf_path)
        official_year = pdf_path.parent.name

        if not doi:
            paper_rows.append(
                {
                    "official_year": official_year,
                    "doi": "",
                    "title": "",
                    "pdf_path": str(pdf_path),
                    "status": "invalid_filename_doi",
                    "crossref_status": "",
                    "reference_count": "",
                    "crossref_reference_count": "",
                    "crossref_is_referenced_by_count": "",
                    "error": "Could not derive DOI from filename",
                    "raw_json_path": "",
                }
            )
            continue

        resolved_query_doi, status, message, error = fetch_work(doi, headers=headers, timeout=args.timeout, max_retries=args.max_retries)
        raw_json_path = raw_dir / f"{sanitize_filename(doi)}.json"

        if message is not None:
            raw_json_path.write_text(json.dumps(message, ensure_ascii=False, indent=2), encoding="utf-8")
            title_list = message.get("title") or []
            title = title_list[0] if title_list else ""
            resolved_doi = message.get("DOI", resolved_query_doi)
            refs = build_reference_rows(
                {
                    "official_year": official_year,
                    "query_doi": doi,
                    "resolved_doi": resolved_doi,
                    "title": title,
                    "pdf_path": pdf_path,
                },
                message,
            )
            reference_rows.extend(refs)
            paper_rows.append(
                {
                    "official_year": official_year,
                    "query_doi": doi,
                    "resolved_doi": resolved_doi,
                    "title": title,
                    "pdf_path": str(pdf_path),
                    "status": "ok",
                    "crossref_status": status,
                    "reference_count": len(refs),
                    "crossref_reference_count": message.get("reference-count", ""),
                    "crossref_is_referenced_by_count": message.get("is-referenced-by-count", ""),
                    "crossref_query_doi": resolved_query_doi,
                    "error": "",
                    "raw_json_path": str(raw_json_path),
                }
            )
        else:
            paper_rows.append(
                {
                    "official_year": official_year,
                    "query_doi": doi,
                    "resolved_doi": "",
                    "title": "",
                    "pdf_path": str(pdf_path),
                    "status": "not_found" if status in {404, 410} else "error",
                    "crossref_status": status,
                    "reference_count": "",
                    "crossref_reference_count": "",
                    "crossref_is_referenced_by_count": "",
                    "crossref_query_doi": resolved_query_doi,
                    "error": error or "",
                    "raw_json_path": "",
                }
            )

        if idx % 25 == 0 or idx == total:
            print(f"{idx}/{total}", file=sys.stderr)
        time.sleep(args.sleep_seconds)

    paper_summary_path = out_dir / "paper_summary.csv"
    references_path = out_dir / "references.csv"
    run_summary_path = out_dir / "run_summary.json"

    with paper_summary_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "official_year",
                "query_doi",
                "resolved_doi",
                "title",
                "pdf_path",
                "status",
                "crossref_status",
                "reference_count",
                "crossref_reference_count",
                "crossref_is_referenced_by_count",
                "crossref_query_doi",
                "error",
                "raw_json_path",
            ],
        )
        writer.writeheader()
        writer.writerows(paper_rows)

    with references_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "citing_official_year",
                "citing_query_doi",
                "citing_resolved_doi",
                "citing_title",
                "citing_pdf_path",
                "reference_index",
                "ref_doi",
                "ref_unstructured",
                "ref_article_title",
                "ref_journal_title",
                "ref_author",
                "ref_year",
                "ref_volume",
                "ref_issue",
                "ref_first_page",
                "ref_key",
                "ref_raw_json",
            ],
        )
        writer.writeheader()
        writer.writerows(reference_rows)

    summary = {
        "pdf_root": str(pdf_root),
        "out_dir": str(out_dir),
        "papers_total": len(paper_rows),
        "papers_ok": sum(1 for row in paper_rows if row["status"] == "ok"),
        "papers_not_found": sum(1 for row in paper_rows if row["status"] == "not_found"),
        "papers_error": sum(1 for row in paper_rows if row["status"] == "error"),
        "papers_invalid_filename_doi": sum(1 for row in paper_rows if row["status"] == "invalid_filename_doi"),
        "references_total": len(reference_rows),
        "paper_summary_csv": str(paper_summary_path),
        "references_csv": str(references_path),
    }
    run_summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
