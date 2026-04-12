import argparse
import csv
import json
import re
from collections import defaultdict

from openai_pdf_runner_utils import normalize_doi, repo_root, write_csv_rows


def pair_id(citing_doi: str, cited_doi: str) -> str:
    value = f"{normalize_doi(citing_doi)}__cites__{normalize_doi(cited_doi)}"
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("._-") or "pair"


def load_csv_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_reference_evidence(rows: list[dict[str, str]], max_examples: int) -> list[dict[str, str]]:
    sorted_rows = sorted(rows, key=lambda row: int(row.get("reference_index") or 0))
    evidence = []
    for row in sorted_rows[:max_examples]:
        evidence.append(
            {
                "reference_index": int(row.get("reference_index") or 0),
                "match_type": row.get("match_type", ""),
                "ref_doi": row.get("ref_doi", ""),
                "ref_article_title": row.get("ref_article_title", ""),
                "ref_unstructured": row.get("ref_unstructured", ""),
            }
        )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paper-summary",
        default="data/jmr_2000_2025/crossref_references/paper_summary.csv",
    )
    parser.add_argument(
        "--notes-manifest",
        default="data/jmr_2000_2025/paper_notes/manifest.csv",
    )
    parser.add_argument(
        "--notes-dir",
        default="data/jmr_2000_2025/paper_notes/runs/ai02_full_notes_conc80/notes",
    )
    parser.add_argument(
        "--internal-edges",
        default="data/jmr_2000_2025/internal_reference_matches/internal_edges.csv",
    )
    parser.add_argument(
        "--matched-references",
        default="data/jmr_2000_2025/internal_reference_matches/matched_references.csv",
    )
    parser.add_argument(
        "--out-path",
        default="data/jmr_2000_2025/citation_triage/manifest.csv",
    )
    parser.add_argument("--max-reference-examples", type=int, default=3)
    args = parser.parse_args()

    root = repo_root()
    paper_summary_path = root / args.paper_summary
    notes_manifest_path = root / args.notes_manifest
    notes_dir = root / args.notes_dir
    internal_edges_path = root / args.internal_edges
    matched_references_path = root / args.matched_references
    out_path = root / args.out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    paper_rows = [row for row in load_csv_rows(paper_summary_path) if row.get("status") == "ok"]
    note_rows = load_csv_rows(notes_manifest_path)
    edge_rows = load_csv_rows(internal_edges_path)
    matched_rows = load_csv_rows(matched_references_path)

    paper_by_doi = {normalize_doi(row["resolved_doi"]): row for row in paper_rows}

    note_by_doi = {}
    missing_note_files = 0
    for row in note_rows:
        doi = normalize_doi(row.get("resolved_doi") or row.get("query_doi"))
        note_path = notes_dir / f"{row['paper_id']}.json"
        if not note_path.exists():
            missing_note_files += 1
            continue
        note_by_doi[doi] = {
            "paper_id": row["paper_id"],
            "note_path": str(note_path),
        }

    matched_by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in matched_rows:
        key = (
            normalize_doi(row["citing_resolved_doi"]),
            normalize_doi(row["cited_resolved_doi"]),
        )
        matched_by_pair[key].append(row)

    manifest_rows = []
    skipped_missing_paper = 0
    skipped_missing_note = 0
    skipped_missing_reference_evidence = 0

    for edge in edge_rows:
        citing_doi = normalize_doi(edge["citing_resolved_doi"])
        cited_doi = normalize_doi(edge["cited_resolved_doi"])
        citing = paper_by_doi.get(citing_doi)
        cited = paper_by_doi.get(cited_doi)
        if not citing or not cited:
            skipped_missing_paper += 1
            continue

        citing_note = note_by_doi.get(citing_doi)
        cited_note = note_by_doi.get(cited_doi)
        if not citing_note or not cited_note:
            skipped_missing_note += 1
            continue

        reference_rows = matched_by_pair.get((citing_doi, cited_doi), [])
        if not reference_rows:
            skipped_missing_reference_evidence += 1
            continue

        manifest_rows.append(
            {
                "pair_id": pair_id(citing["resolved_doi"], cited["resolved_doi"]),
                "citing_official_year": citing["official_year"],
                "citing_query_doi": citing["query_doi"],
                "citing_resolved_doi": citing["resolved_doi"],
                "citing_title": citing["title"],
                "citing_pdf_path": citing["pdf_path"],
                "citing_note_path": citing_note["note_path"],
                "cited_official_year": cited["official_year"],
                "cited_query_doi": cited["query_doi"],
                "cited_resolved_doi": cited["resolved_doi"],
                "cited_title": cited["title"],
                "cited_pdf_path": cited["pdf_path"],
                "cited_note_path": cited_note["note_path"],
                "matched_reference_count": edge["matched_reference_count"],
                "match_type_breakdown": edge["match_type_breakdown"],
                "matched_reference_evidence_json": json.dumps(
                    build_reference_evidence(reference_rows, args.max_reference_examples),
                    ensure_ascii=False,
                ),
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
        "paper_summary_path": str(paper_summary_path),
        "notes_manifest_path": str(notes_manifest_path),
        "notes_dir": str(notes_dir),
        "internal_edges_path": str(internal_edges_path),
        "matched_references_path": str(matched_references_path),
        "manifest_path": str(out_path),
        "paper_rows_ok": len(paper_rows),
        "note_rows": len(note_rows),
        "edge_rows": len(edge_rows),
        "matched_reference_rows": len(matched_rows),
        "manifest_rows": len(manifest_rows),
        "missing_note_files_in_note_run": missing_note_files,
        "skipped_missing_paper": skipped_missing_paper,
        "skipped_missing_note": skipped_missing_note,
        "skipped_missing_reference_evidence": skipped_missing_reference_evidence,
        "max_reference_examples": args.max_reference_examples,
    }
    (out_path.parent / "manifest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
