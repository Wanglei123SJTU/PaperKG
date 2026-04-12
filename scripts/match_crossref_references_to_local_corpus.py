import argparse
import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    value = value.strip().strip("/")
    return value or None


def normalize_title(value: str | None) -> str | None:
    if not value:
        return None
    value = value.lower()
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[\u2018\u2019\u201b\u2032]", "'", value)
    value = re.sub(r"[\u201c\u201d\u2033]", '"', value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def build_local_indexes(paper_rows: list[dict]) -> tuple[dict[str, dict], dict[str, dict], Counter]:
    doi_index: dict[str, dict] = {}
    title_buckets: defaultdict[str, list[dict]] = defaultdict(list)

    for row in paper_rows:
        for doi in (normalize_doi(row.get("query_doi")), normalize_doi(row.get("resolved_doi"))):
            if doi:
                doi_index[doi] = row
        title = normalize_title(row.get("title"))
        if title:
            title_buckets[title].append(row)

    unique_title_index = {title: rows[0] for title, rows in title_buckets.items() if len(rows) == 1}
    title_ambiguity_counter = Counter({title: len(rows) for title, rows in title_buckets.items() if len(rows) > 1})
    return doi_index, unique_title_index, title_ambiguity_counter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paper-summary",
        default="data/jmr_2000_2025/crossref_references/paper_summary.csv",
    )
    parser.add_argument(
        "--references",
        default="data/jmr_2000_2025/crossref_references/references.csv",
    )
    parser.add_argument(
        "--out-dir",
        default="data/jmr_2000_2025/internal_reference_matches",
    )
    args = parser.parse_args()

    paper_summary_path = Path(args.paper_summary)
    references_path = Path(args.references)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paper_rows = list(csv.DictReader(paper_summary_path.open("r", encoding="utf-8-sig", newline="")))
    paper_rows = [row for row in paper_rows if row.get("status") == "ok"]
    reference_rows = list(csv.DictReader(references_path.open("r", encoding="utf-8-sig", newline="")))

    doi_index, unique_title_index, title_ambiguity_counter = build_local_indexes(paper_rows)

    matched_rows: list[dict] = []
    unmatched_rows: list[dict] = []
    counts = Counter()

    for ref in reference_rows:
        cited = None
        match_type = ""
        norm_ref_doi = normalize_doi(ref.get("ref_doi"))
        norm_ref_title = normalize_title(ref.get("ref_article_title"))

        if norm_ref_doi:
            counts["references_with_ref_doi"] += 1
            cited = doi_index.get(norm_ref_doi)
            if cited:
                match_type = "doi"
                counts["matched_by_doi"] += 1
            else:
                counts["unmatched_with_ref_doi"] += 1

        if not cited and norm_ref_title:
            counts["references_with_ref_article_title"] += 1
            if norm_ref_title in unique_title_index:
                cited = unique_title_index[norm_ref_title]
                match_type = "title"
                counts["matched_by_title"] += 1
            elif norm_ref_title in title_ambiguity_counter:
                counts["ambiguous_title_refs"] += 1

        if cited:
            matched_rows.append(
                {
                    "citing_official_year": ref["citing_official_year"],
                    "citing_query_doi": ref["citing_query_doi"],
                    "citing_resolved_doi": ref["citing_resolved_doi"],
                    "citing_title": ref["citing_title"],
                    "citing_pdf_path": ref["citing_pdf_path"],
                    "reference_index": ref["reference_index"],
                    "match_type": match_type,
                    "ref_doi": ref.get("ref_doi", ""),
                    "ref_article_title": ref.get("ref_article_title", ""),
                    "ref_unstructured": ref.get("ref_unstructured", ""),
                    "cited_official_year": cited["official_year"],
                    "cited_query_doi": cited["query_doi"],
                    "cited_resolved_doi": cited["resolved_doi"],
                    "cited_title": cited["title"],
                    "cited_pdf_path": cited["pdf_path"],
                }
            )
        else:
            unmatched_rows.append(
                {
                    "citing_official_year": ref["citing_official_year"],
                    "citing_resolved_doi": ref["citing_resolved_doi"],
                    "citing_title": ref["citing_title"],
                    "reference_index": ref["reference_index"],
                    "ref_doi": ref.get("ref_doi", ""),
                    "ref_article_title": ref.get("ref_article_title", ""),
                    "ref_unstructured": ref.get("ref_unstructured", ""),
                }
            )

    edge_buckets: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    incoming_counts = Counter()
    outgoing_counts = Counter()

    for row in matched_rows:
        key = (row["citing_resolved_doi"], row["cited_resolved_doi"])
        edge_buckets[key].append(row)

    edge_rows = []
    for (citing_doi, cited_doi), rows in edge_buckets.items():
        first = rows[0]
        match_type_counts = Counter(row["match_type"] for row in rows)
        edge_rows.append(
            {
                "citing_official_year": first["citing_official_year"],
                "citing_resolved_doi": citing_doi,
                "citing_title": first["citing_title"],
                "cited_official_year": first["cited_official_year"],
                "cited_resolved_doi": cited_doi,
                "cited_title": first["cited_title"],
                "matched_reference_count": len(rows),
                "match_type_breakdown": json.dumps(match_type_counts, ensure_ascii=False, sort_keys=True),
            }
        )
        outgoing_counts[citing_doi] += 1
        incoming_counts[cited_doi] += 1

    paper_by_resolved_doi = {normalize_doi(row["resolved_doi"]): row for row in paper_rows}

    top_incoming = sorted(
        (
            {
                "resolved_doi": doi,
                "title": paper_by_resolved_doi[normalize_doi(doi)]["title"],
                "official_year": int(paper_by_resolved_doi[normalize_doi(doi)]["official_year"]),
                "incoming_internal_match_count": count,
            }
            for doi, count in incoming_counts.items()
        ),
        key=lambda x: (-x["incoming_internal_match_count"], x["official_year"], x["title"]),
    )[:15]

    top_outgoing = sorted(
        (
            {
                "resolved_doi": doi,
                "title": paper_by_resolved_doi[normalize_doi(doi)]["title"],
                "official_year": int(paper_by_resolved_doi[normalize_doi(doi)]["official_year"]),
                "outgoing_internal_match_count": count,
            }
            for doi, count in outgoing_counts.items()
        ),
        key=lambda x: (-x["outgoing_internal_match_count"], x["official_year"], x["title"]),
    )[:15]

    matched_per_paper = Counter(row["citing_resolved_doi"] for row in matched_rows)
    matched_ref_counts = [matched_per_paper.get(row["resolved_doi"], 0) for row in paper_rows]

    summary = {
        "papers_in_local_corpus": len(paper_rows),
        "references_total": len(reference_rows),
        "matched_reference_rows": len(matched_rows),
        "unmatched_reference_rows": len(unmatched_rows),
        "reference_match_rate_pct": round(len(matched_rows) / len(reference_rows) * 100, 2) if reference_rows else 0,
        "references_with_ref_doi": counts["references_with_ref_doi"],
        "matched_by_doi": counts["matched_by_doi"],
        "doi_match_rate_within_doi_refs_pct": round(counts["matched_by_doi"] / counts["references_with_ref_doi"] * 100, 2) if counts["references_with_ref_doi"] else 0,
        "references_with_ref_article_title": counts["references_with_ref_article_title"],
        "matched_by_title": counts["matched_by_title"],
        "ambiguous_title_refs": counts["ambiguous_title_refs"],
        "unique_directed_internal_edges": len(edge_rows),
        "papers_with_outgoing_internal_matches": sum(1 for row in paper_rows if outgoing_counts.get(row["resolved_doi"], 0) > 0),
        "papers_with_incoming_internal_matches": sum(1 for row in paper_rows if incoming_counts.get(row["resolved_doi"], 0) > 0),
        "matched_references_per_paper": {
            "mean": round(statistics.mean(matched_ref_counts), 2) if matched_ref_counts else 0,
            "median": statistics.median(matched_ref_counts) if matched_ref_counts else 0,
            "max": max(matched_ref_counts) if matched_ref_counts else 0,
        },
        "top_15_by_incoming_internal_matches": top_incoming,
        "top_15_by_outgoing_internal_matches": top_outgoing,
    }

    matched_path = out_dir / "matched_references.csv"
    unmatched_path = out_dir / "unmatched_references.csv"
    edges_path = out_dir / "internal_edges.csv"
    summary_path = out_dir / "summary.json"

    with matched_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "citing_official_year",
                "citing_query_doi",
                "citing_resolved_doi",
                "citing_title",
                "citing_pdf_path",
                "reference_index",
                "match_type",
                "ref_doi",
                "ref_article_title",
                "ref_unstructured",
                "cited_official_year",
                "cited_query_doi",
                "cited_resolved_doi",
                "cited_title",
                "cited_pdf_path",
            ],
        )
        writer.writeheader()
        writer.writerows(matched_rows)

    with unmatched_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "citing_official_year",
                "citing_resolved_doi",
                "citing_title",
                "reference_index",
                "ref_doi",
                "ref_article_title",
                "ref_unstructured",
            ],
        )
        writer.writeheader()
        writer.writerows(unmatched_rows)

    with edges_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "citing_official_year",
                "citing_resolved_doi",
                "citing_title",
                "cited_official_year",
                "cited_resolved_doi",
                "cited_title",
                "matched_reference_count",
                "match_type_breakdown",
            ],
        )
        writer.writeheader()
        writer.writerows(sorted(edge_rows, key=lambda r: (int(r["citing_official_year"]), r["citing_resolved_doi"], r["cited_resolved_doi"])))

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "matched_path": str(matched_path), "edges_path": str(edges_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
