import argparse
import json

from openai_pdf_runner_utils import repo_root, sanitize_filename, write_csv_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paper-summary",
        default="data/jmr_2000_2025/crossref_references/paper_summary.csv",
    )
    parser.add_argument(
        "--out-path",
        default="data/jmr_2000_2025/paper_notes/manifest.csv",
    )
    args = parser.parse_args()

    root = repo_root()
    paper_summary_path = root / args.paper_summary
    out_path = root / args.out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import csv

    with paper_summary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("status") == "ok"]

    manifest_rows = []
    skipped_missing_pdf = 0
    for row in rows:
        pdf_path = root / row["pdf_path"]
        if not pdf_path.exists():
            skipped_missing_pdf += 1
            continue

        item_doi = row.get("resolved_doi") or row.get("query_doi") or row.get("title") or pdf_path.stem
        manifest_rows.append(
            {
                "paper_id": sanitize_filename(item_doi),
                "official_year": row["official_year"],
                "query_doi": row["query_doi"],
                "resolved_doi": row["resolved_doi"],
                "title": row["title"],
                "pdf_path": row["pdf_path"],
            }
        )

    manifest_rows.sort(key=lambda row: (int(row["official_year"]), row["resolved_doi"], row["title"]))

    write_csv_rows(
        out_path,
        ["paper_id", "official_year", "query_doi", "resolved_doi", "title", "pdf_path"],
        manifest_rows,
    )

    summary = {
        "paper_summary_path": str(paper_summary_path),
        "manifest_path": str(out_path),
        "papers_total_ok": len(rows),
        "manifest_rows": len(manifest_rows),
        "skipped_missing_pdf": skipped_missing_pdf,
    }
    (out_path.parent / "manifest_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
