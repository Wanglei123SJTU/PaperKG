import argparse
import csv
import json
from pathlib import Path

from openai_pdf_runner_utils import repo_root, write_csv_rows


def resolve_maybe_absolute(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--triage-manifest",
        default="data/jmr_2000_2025/citation_triage/manifest.csv",
    )
    parser.add_argument(
        "--triage-summary",
        default="data/jmr_2000_2025/citation_triage/runs/ai02_full_triage_conc80/summary.csv",
    )
    parser.add_argument(
        "--include-decisions",
        default="keep_for_relation_judgment,uncertain",
        help="Comma-separated triage decisions to keep for final judgment.",
    )
    parser.add_argument(
        "--out-path",
        default="data/jmr_2000_2025/citation_judgments/manifest.csv",
    )
    args = parser.parse_args()

    root = repo_root()
    triage_manifest_path = root / args.triage_manifest
    triage_summary_path = root / args.triage_summary
    out_path = root / args.out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    include_decisions = {value.strip() for value in args.include_decisions.split(",") if value.strip()}

    with triage_manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        triage_manifest_rows = list(csv.DictReader(handle))
    with triage_summary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        triage_summary_rows = list(csv.DictReader(handle))

    manifest_by_pair = {row["pair_id"]: row for row in triage_manifest_rows}

    manifest_rows: list[dict[str, str]] = []
    skipped_nonselected = 0
    skipped_missing_manifest = 0
    skipped_missing_citing_pdf = 0
    skipped_missing_cited_note = 0

    for summary_row in triage_summary_rows:
        if summary_row.get("status") != "ok":
            skipped_nonselected += 1
            continue
        triage_decision = (summary_row.get("triage_decision") or "").strip()
        if triage_decision not in include_decisions:
            skipped_nonselected += 1
            continue

        pair_id = summary_row["pair_id"]
        manifest_row = manifest_by_pair.get(pair_id)
        if not manifest_row:
            skipped_missing_manifest += 1
            continue

        citing_pdf_path = resolve_maybe_absolute(root, manifest_row["citing_pdf_path"])
        cited_note_path = resolve_maybe_absolute(root, manifest_row["cited_note_path"])
        if not citing_pdf_path.exists():
            skipped_missing_citing_pdf += 1
            continue
        if not cited_note_path.exists():
            skipped_missing_cited_note += 1
            continue

        manifest_rows.append(
            {
                "pair_id": pair_id,
                "triage_decision": triage_decision,
                "citing_official_year": manifest_row["citing_official_year"],
                "citing_query_doi": manifest_row["citing_query_doi"],
                "citing_resolved_doi": manifest_row["citing_resolved_doi"],
                "citing_title": manifest_row["citing_title"],
                "citing_pdf_path": manifest_row["citing_pdf_path"],
                "citing_note_path": manifest_row["citing_note_path"],
                "cited_official_year": manifest_row["cited_official_year"],
                "cited_query_doi": manifest_row["cited_query_doi"],
                "cited_resolved_doi": manifest_row["cited_resolved_doi"],
                "cited_title": manifest_row["cited_title"],
                "cited_pdf_path": manifest_row["cited_pdf_path"],
                "cited_note_path": manifest_row["cited_note_path"],
                "matched_reference_count": manifest_row["matched_reference_count"],
                "match_type_breakdown": manifest_row["match_type_breakdown"],
                "matched_reference_evidence_json": manifest_row["matched_reference_evidence_json"],
            }
        )

    manifest_rows.sort(
        key=lambda row: (
            int(row["citing_official_year"]),
            row["citing_resolved_doi"],
            int(row["cited_official_year"]),
            row["cited_resolved_doi"],
        )
    )

    fieldnames = [
        "pair_id",
        "triage_decision",
        "citing_official_year",
        "citing_query_doi",
        "citing_resolved_doi",
        "citing_title",
        "citing_pdf_path",
        "citing_note_path",
        "cited_official_year",
        "cited_query_doi",
        "cited_resolved_doi",
        "cited_title",
        "cited_pdf_path",
        "cited_note_path",
        "matched_reference_count",
        "match_type_breakdown",
        "matched_reference_evidence_json",
    ]
    write_csv_rows(out_path, fieldnames, manifest_rows)

    summary = {
        "triage_manifest_path": str(triage_manifest_path),
        "triage_summary_path": str(triage_summary_path),
        "manifest_path": str(out_path),
        "include_decisions": sorted(include_decisions),
        "triage_manifest_rows": len(triage_manifest_rows),
        "triage_summary_rows": len(triage_summary_rows),
        "manifest_rows": len(manifest_rows),
        "skipped_nonselected": skipped_nonselected,
        "skipped_missing_manifest": skipped_missing_manifest,
        "skipped_missing_citing_pdf": skipped_missing_citing_pdf,
        "skipped_missing_cited_note": skipped_missing_cited_note,
    }
    (out_path.parent / "manifest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
