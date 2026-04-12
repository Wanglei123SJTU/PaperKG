import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip().strip("/")


def sanitize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def strip_tags(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def safe_int(value: Any) -> int | None:
    text = sanitize_text(value)
    if not text:
        return None
    return int(text)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_paper_row(root: Path, paper_row: dict[str, str]) -> dict[str, Any]:
    paper_id = normalize_doi(paper_row.get("resolved_doi") or paper_row.get("query_doi"))
    raw_json_path = root / paper_row["raw_json_path"]
    raw_metadata = load_json(raw_json_path) if raw_json_path.exists() else {}
    authors = raw_metadata.get("author") or []
    author_names = []
    for author in authors:
        given = sanitize_text(author.get("given"))
        family = sanitize_text(author.get("family"))
        full = " ".join(part for part in [given, family] if part)
        if full:
            author_names.append(full)
    title_list = raw_metadata.get("title") or []
    container_list = raw_metadata.get("container-title") or []
    return {
        "paper_id": paper_id,
        "openalex_id": paper_id,
        "query_doi": sanitize_text(paper_row.get("query_doi")),
        "resolved_doi": sanitize_text(paper_row.get("resolved_doi")),
        "doi_norm": paper_id,
        "doi_uri": f"https://doi.org/{paper_id}" if paper_id else "",
        "title": sanitize_text(paper_row.get("title")) or sanitize_text(title_list[0] if title_list else ""),
        "official_year": safe_int(paper_row.get("official_year")),
        "journal": sanitize_text(container_list[0] if container_list else "Journal of Marketing Research"),
        "volume": sanitize_text(raw_metadata.get("volume")),
        "issue": sanitize_text(raw_metadata.get("issue")),
        "authors_json": json.dumps(author_names, ensure_ascii=False),
        "abstract_text": strip_tags(sanitize_text(raw_metadata.get("abstract"))),
        "pdf_snapshot_path": sanitize_text(paper_row.get("pdf_path")),
        "crossref_reference_count": safe_int(paper_row.get("crossref_reference_count")),
        "crossref_is_referenced_by_count": safe_int(paper_row.get("crossref_is_referenced_by_count")),
        "raw_json_path": sanitize_text(paper_row.get("raw_json_path")),
        "raw_metadata_json": json.dumps(raw_metadata, ensure_ascii=False),
    }


def build_note_row(paper_id: str, note_path: Path, run_name: str) -> dict[str, Any]:
    note = load_json(note_path)
    return {
        "paper_id": paper_id,
        "openalex_id": paper_id,
        "one_line_summary": sanitize_text(note.get("one_line_summary")),
        "research_question": sanitize_text(note.get("research_question")),
        "research_gap": sanitize_text(note.get("research_gap")),
        "focal_constructs_json": json.dumps(note.get("focal_constructs") or [], ensure_ascii=False),
        "context": sanitize_text(note.get("context")),
        "design_and_data": sanitize_text(note.get("design_and_data")),
        "main_findings_json": json.dumps(note.get("main_findings") or [], ensure_ascii=False),
        "claimed_contribution_json": json.dumps(note.get("claimed_contribution") or [], ensure_ascii=False),
        "relation_to_prior_work": sanitize_text(note.get("relation_to_prior_work")),
        "generation_json": json.dumps({"run_name": run_name, "source": "paper_note"}, ensure_ascii=False),
        "note_json": json.dumps(note, ensure_ascii=False),
        "validation_errors_json": json.dumps([], ensure_ascii=False),
        "note_path": str(note_path),
    }


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        DROP TABLE IF EXISTS papers;
        DROP TABLE IF EXISTS paper_notes;
        DROP TABLE IF EXISTS raw_internal_citations;
        DROP TABLE IF EXISTS citation_judgments;
        DROP TABLE IF EXISTS substantive_edges;
        DROP TABLE IF EXISTS paper_search;

        CREATE TABLE papers (
            paper_id TEXT PRIMARY KEY,
            openalex_id TEXT NOT NULL UNIQUE,
            query_doi TEXT,
            resolved_doi TEXT,
            doi_norm TEXT,
            doi_uri TEXT,
            title TEXT NOT NULL,
            official_year INTEGER,
            journal TEXT,
            volume TEXT,
            issue TEXT,
            authors_json TEXT,
            abstract_text TEXT,
            pdf_snapshot_path TEXT,
            crossref_reference_count INTEGER,
            crossref_is_referenced_by_count INTEGER,
            raw_json_path TEXT,
            raw_metadata_json TEXT
        );

        CREATE TABLE paper_notes (
            paper_id TEXT PRIMARY KEY,
            openalex_id TEXT NOT NULL UNIQUE,
            one_line_summary TEXT,
            research_question TEXT,
            research_gap TEXT,
            focal_constructs_json TEXT,
            context TEXT,
            design_and_data TEXT,
            main_findings_json TEXT,
            claimed_contribution_json TEXT,
            relation_to_prior_work TEXT,
            generation_json TEXT,
            note_json TEXT,
            validation_errors_json TEXT,
            note_path TEXT
        );

        CREATE TABLE raw_internal_citations (
            pair_id TEXT PRIMARY KEY,
            citing_openalex_id TEXT NOT NULL,
            cited_openalex_id TEXT NOT NULL,
            citing_doi_uri TEXT,
            cited_doi_uri TEXT,
            citing_title TEXT,
            cited_title TEXT,
            citing_official_year INTEGER,
            cited_official_year INTEGER,
            matched_reference_count INTEGER,
            match_type_breakdown TEXT,
            matched_reference_evidence_json TEXT
        );

        CREATE TABLE citation_judgments (
            pair_id TEXT PRIMARY KEY,
            citing_openalex_id TEXT NOT NULL,
            cited_openalex_id TEXT NOT NULL,
            citation_substance TEXT NOT NULL,
            relation_type TEXT,
            relation_description TEXT,
            rationale TEXT,
            model TEXT,
            requested_reasoning_effort TEXT,
            returned_reasoning_effort TEXT,
            api_key_slot INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            judgment_path TEXT,
            raw_response_path TEXT
        );

        CREATE TABLE substantive_edges (
            pair_id TEXT PRIMARY KEY,
            citing_openalex_id TEXT NOT NULL,
            cited_openalex_id TEXT NOT NULL,
            citing_doi_uri TEXT,
            cited_doi_uri TEXT,
            citing_title TEXT,
            cited_title TEXT,
            citing_official_year INTEGER,
            cited_official_year INTEGER,
            matched_reference_count INTEGER,
            match_type_breakdown TEXT,
            matched_reference_evidence_json TEXT,
            citation_substance TEXT NOT NULL,
            relation_type TEXT,
            relation_description TEXT,
            rationale TEXT
        );

        CREATE VIRTUAL TABLE paper_search USING fts5(
            openalex_id UNINDEXED,
            title,
            abstract_text,
            one_line_summary,
            research_question,
            research_gap,
            relation_to_prior_work,
            design_and_data,
            context,
            focal_constructs,
            main_findings,
            claimed_contribution
        );

        CREATE INDEX idx_papers_doi_norm ON papers(doi_norm);
        CREATE INDEX idx_papers_title ON papers(title);
        CREATE INDEX idx_notes_openalex_id ON paper_notes(openalex_id);
        CREATE INDEX idx_raw_internal_citations_citing ON raw_internal_citations(citing_openalex_id);
        CREATE INDEX idx_raw_internal_citations_cited ON raw_internal_citations(cited_openalex_id);
        CREATE INDEX idx_citation_judgments_citing ON citation_judgments(citing_openalex_id);
        CREATE INDEX idx_citation_judgments_cited ON citation_judgments(cited_openalex_id);
        CREATE INDEX idx_substantive_edges_citing ON substantive_edges(citing_openalex_id);
        CREATE INDEX idx_substantive_edges_cited ON substantive_edges(cited_openalex_id);
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-summary", default="data/jmr_2000_2025/crossref_references/paper_summary.csv")
    parser.add_argument("--notes-dir", default="data/jmr_2000_2025/paper_notes/runs/ai02_full_notes_conc80/notes")
    parser.add_argument("--notes-run-name", default="ai02_full_notes_conc80")
    parser.add_argument("--raw-citations-manifest", default="data/jmr_2000_2025/citation_triage/manifest.csv")
    parser.add_argument("--judgment-manifest", default="data/jmr_2000_2025/citation_judgments/manifest.csv")
    parser.add_argument("--judgment-summary", default="data/jmr_2000_2025/citation_judgments/runs/ai02_full_judgments_one_pdf_note_three_keys_conc240/summary.csv")
    parser.add_argument("--out-db", default="data/jmr_2000_2025/paperkg_base/paperkg.sqlite")
    args = parser.parse_args()

    paper_summary_path = ROOT / args.paper_summary
    notes_dir = ROOT / args.notes_dir
    raw_citations_manifest_path = ROOT / args.raw_citations_manifest
    judgment_manifest_path = ROOT / args.judgment_manifest
    judgment_summary_path = ROOT / args.judgment_summary
    out_db_path = ROOT / args.out_db
    out_db_path.parent.mkdir(parents=True, exist_ok=True)
    if out_db_path.exists():
        out_db_path.unlink()

    paper_summary_rows = [row for row in load_csv_rows(paper_summary_path) if row.get("status") == "ok"]
    raw_citation_rows = load_csv_rows(raw_citations_manifest_path)
    judgment_manifest_rows = load_csv_rows(judgment_manifest_path)
    judgment_summary_rows = [row for row in load_csv_rows(judgment_summary_path) if row.get("status") == "ok"]

    paper_rows = []
    paper_ids = set()
    for row in paper_summary_rows:
        paper_row = build_paper_row(ROOT, row)
        if not paper_row["paper_id"]:
            continue
        paper_rows.append(paper_row)
        paper_ids.add(paper_row["paper_id"])

    note_rows = []
    skipped_missing_note = 0
    for paper_row in paper_rows:
        note_path = notes_dir / (paper_row["paper_id"].replace("/", "_") + ".json")
        if not note_path.exists():
            skipped_missing_note += 1
            continue
        note_rows.append(build_note_row(paper_row["paper_id"], note_path, args.notes_run_name))

    raw_internal_rows = []
    for row in raw_citation_rows:
        citing_id = normalize_doi(row.get("citing_resolved_doi"))
        cited_id = normalize_doi(row.get("cited_resolved_doi"))
        if citing_id not in paper_ids or cited_id not in paper_ids:
            continue
        raw_internal_rows.append(
            {
                "pair_id": row["pair_id"],
                "citing_openalex_id": citing_id,
                "cited_openalex_id": cited_id,
                "citing_doi_uri": f"https://doi.org/{citing_id}",
                "cited_doi_uri": f"https://doi.org/{cited_id}",
                "citing_title": row["citing_title"],
                "cited_title": row["cited_title"],
                "citing_official_year": safe_int(row["citing_official_year"]),
                "cited_official_year": safe_int(row["cited_official_year"]),
                "matched_reference_count": safe_int(row["matched_reference_count"]) or 0,
                "match_type_breakdown": row["match_type_breakdown"],
                "matched_reference_evidence_json": row["matched_reference_evidence_json"],
            }
        )

    judgment_manifest_by_pair = {row["pair_id"]: row for row in judgment_manifest_rows}
    raw_internal_by_pair = {row["pair_id"]: row for row in raw_internal_rows}
    judgment_rows = []
    substantive_rows = []
    for row in judgment_summary_rows:
        pair_id = row["pair_id"]
        manifest_row = judgment_manifest_by_pair.get(pair_id)
        raw_row = raw_internal_by_pair.get(pair_id)
        judgment_path = Path(row["output_path"])
        if not manifest_row or not raw_row or not judgment_path.exists():
            continue
        payload = load_json(judgment_path)
        citing_id = normalize_doi(manifest_row["citing_resolved_doi"])
        cited_id = normalize_doi(manifest_row["cited_resolved_doi"])
        judgment_row = {
            "pair_id": pair_id,
            "citing_openalex_id": citing_id,
            "cited_openalex_id": cited_id,
            "citation_substance": payload["citation_substance"],
            "relation_type": payload.get("relation_type"),
            "relation_description": payload.get("relation_description"),
            "rationale": payload.get("rationale"),
            "model": row.get("model"),
            "requested_reasoning_effort": row.get("requested_reasoning_effort"),
            "returned_reasoning_effort": row.get("returned_reasoning_effort"),
            "api_key_slot": safe_int(row.get("api_key_slot")),
            "input_tokens": safe_int(row.get("input_tokens")),
            "output_tokens": safe_int(row.get("output_tokens")),
            "total_tokens": safe_int(row.get("total_tokens")),
            "judgment_path": row.get("output_path"),
            "raw_response_path": row.get("raw_response_path"),
        }
        judgment_rows.append(judgment_row)
        if payload["citation_substance"] == "substantive":
            substantive_rows.append(
                {
                    **raw_row,
                    "citation_substance": payload["citation_substance"],
                    "relation_type": payload.get("relation_type"),
                    "relation_description": payload.get("relation_description"),
                    "rationale": payload.get("rationale"),
                }
            )

    conn = sqlite3.connect(out_db_path)
    try:
        create_schema(conn)
        conn.executemany(
            """
            INSERT INTO papers (
                paper_id, openalex_id, query_doi, resolved_doi, doi_norm, doi_uri, title, official_year,
                journal, volume, issue, authors_json, abstract_text, pdf_snapshot_path,
                crossref_reference_count, crossref_is_referenced_by_count, raw_json_path, raw_metadata_json
            ) VALUES (
                :paper_id, :openalex_id, :query_doi, :resolved_doi, :doi_norm, :doi_uri, :title, :official_year,
                :journal, :volume, :issue, :authors_json, :abstract_text, :pdf_snapshot_path,
                :crossref_reference_count, :crossref_is_referenced_by_count, :raw_json_path, :raw_metadata_json
            )
            """,
            paper_rows,
        )
        conn.executemany(
            """
            INSERT INTO paper_notes (
                paper_id, openalex_id, one_line_summary, research_question, research_gap, focal_constructs_json,
                context, design_and_data, main_findings_json, claimed_contribution_json, relation_to_prior_work,
                generation_json, note_json, validation_errors_json, note_path
            ) VALUES (
                :paper_id, :openalex_id, :one_line_summary, :research_question, :research_gap, :focal_constructs_json,
                :context, :design_and_data, :main_findings_json, :claimed_contribution_json, :relation_to_prior_work,
                :generation_json, :note_json, :validation_errors_json, :note_path
            )
            """,
            note_rows,
        )
        conn.executemany(
            """
            INSERT INTO raw_internal_citations (
                pair_id, citing_openalex_id, cited_openalex_id, citing_doi_uri, cited_doi_uri, citing_title,
                cited_title, citing_official_year, cited_official_year, matched_reference_count,
                match_type_breakdown, matched_reference_evidence_json
            ) VALUES (
                :pair_id, :citing_openalex_id, :cited_openalex_id, :citing_doi_uri, :cited_doi_uri, :citing_title,
                :cited_title, :citing_official_year, :cited_official_year, :matched_reference_count,
                :match_type_breakdown, :matched_reference_evidence_json
            )
            """,
            raw_internal_rows,
        )
        conn.executemany(
            """
            INSERT INTO citation_judgments (
                pair_id, citing_openalex_id, cited_openalex_id, citation_substance, relation_type,
                relation_description, rationale, model, requested_reasoning_effort, returned_reasoning_effort,
                api_key_slot, input_tokens, output_tokens, total_tokens, judgment_path, raw_response_path
            ) VALUES (
                :pair_id, :citing_openalex_id, :cited_openalex_id, :citation_substance, :relation_type,
                :relation_description, :rationale, :model, :requested_reasoning_effort, :returned_reasoning_effort,
                :api_key_slot, :input_tokens, :output_tokens, :total_tokens, :judgment_path, :raw_response_path
            )
            """,
            judgment_rows,
        )
        conn.executemany(
            """
            INSERT INTO substantive_edges (
                pair_id, citing_openalex_id, cited_openalex_id, citing_doi_uri, cited_doi_uri, citing_title,
                cited_title, citing_official_year, cited_official_year, matched_reference_count,
                match_type_breakdown, matched_reference_evidence_json, citation_substance, relation_type,
                relation_description, rationale
            ) VALUES (
                :pair_id, :citing_openalex_id, :cited_openalex_id, :citing_doi_uri, :cited_doi_uri, :citing_title,
                :cited_title, :citing_official_year, :cited_official_year, :matched_reference_count,
                :match_type_breakdown, :matched_reference_evidence_json, :citation_substance, :relation_type,
                :relation_description, :rationale
            )
            """,
            substantive_rows,
        )

        paper_search_rows = []
        notes_by_id = {row["paper_id"]: row for row in note_rows}
        for paper in paper_rows:
            note = notes_by_id.get(paper["paper_id"], {})
            paper_search_rows.append(
                (
                    paper["openalex_id"],
                    paper["title"],
                    paper["abstract_text"],
                    note.get("one_line_summary", ""),
                    note.get("research_question", ""),
                    note.get("research_gap", ""),
                    note.get("relation_to_prior_work", ""),
                    note.get("design_and_data", ""),
                    note.get("context", ""),
                    " ".join(json.loads(note.get("focal_constructs_json", "[]"))),
                    " ".join(json.loads(note.get("main_findings_json", "[]"))),
                    " ".join(json.loads(note.get("claimed_contribution_json", "[]"))),
                )
            )
        conn.executemany(
            """
            INSERT INTO paper_search (
                openalex_id, title, abstract_text, one_line_summary, research_question, research_gap,
                relation_to_prior_work, design_and_data, context, focal_constructs, main_findings, claimed_contribution
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            paper_search_rows,
        )
        conn.commit()
    finally:
        conn.close()

    manifest = {
        "paper_summary_path": str(paper_summary_path),
        "notes_dir": str(notes_dir),
        "raw_citations_manifest_path": str(raw_citations_manifest_path),
        "judgment_manifest_path": str(judgment_manifest_path),
        "judgment_summary_path": str(judgment_summary_path),
        "sqlite_path": str(out_db_path),
        "paper_count": len(paper_rows),
        "note_count": len(note_rows),
        "raw_internal_citation_count": len(raw_internal_rows),
        "citation_judgment_count": len(judgment_rows),
        "substantive_edge_count": len(substantive_rows),
        "skipped_missing_note": skipped_missing_note,
    }
    (out_db_path.parent / "paperkg.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
