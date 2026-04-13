from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    prefix = "https://doi.org/"
    if value.lower().startswith(prefix):
        return value[len(prefix) :].lower()
    return value.lower()


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def quote_fts_query(query: str) -> str:
    tokens = [token.strip().replace('"', '""') for token in query.split() if token.strip()]
    if not tokens:
        return ""
    return " AND ".join(f'"{token}"' for token in tokens)


class PaperKGStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def _parse_json_field(self, value: str | None) -> Any:
        if not value:
            return None
        return json.loads(value)

    def _hydrate_paper(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["paper_id"] = payload.get("paper_id") or payload.get("openalex_id")
        payload["resolved_doi"] = payload.get("resolved_doi") or payload.get("doi_norm")
        payload["authors"] = self._parse_json_field(payload.get("authors_json"))
        payload.pop("authors_json", None)
        payload["raw_metadata"] = self._parse_json_field(payload.get("raw_metadata_json"))
        payload.pop("raw_metadata_json", None)
        return payload

    def _hydrate_note(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = dict(row)
        payload["generation"] = self._parse_json_field(payload.get("generation_json"))
        payload.pop("generation_json", None)
        payload["focal_constructs"] = self._parse_json_field(payload.get("focal_constructs_json")) or []
        payload.pop("focal_constructs_json", None)
        payload["main_findings"] = self._parse_json_field(payload.get("main_findings_json")) or []
        payload.pop("main_findings_json", None)
        payload["claimed_contribution"] = self._parse_json_field(payload.get("claimed_contribution_json")) or []
        payload.pop("claimed_contribution_json", None)
        payload["note"] = self._parse_json_field(payload.get("note_json"))
        payload.pop("note_json", None)
        payload["validation_errors"] = self._parse_json_field(payload.get("validation_errors_json")) or []
        payload.pop("validation_errors_json", None)
        return payload

    def _hydrate_edge(self, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = dict(row)
        if "match_type_breakdown" in payload:
            payload["match_type_breakdown"] = self._parse_json_field(payload.get("match_type_breakdown")) or {}
        if "matched_reference_evidence_json" in payload:
            payload["matched_reference_evidence"] = self._parse_json_field(payload.get("matched_reference_evidence_json")) or []
            payload.pop("matched_reference_evidence_json", None)
        return payload

    def resolve_paper(self, identifier: str) -> dict[str, Any] | None:
        identifier = identifier.strip()
        doi_norm = normalize_doi(identifier)
        if doi_norm:
            row = self.conn.execute("SELECT * FROM papers WHERE doi_norm = ? OR paper_id = ?", (doi_norm, doi_norm)).fetchone()
            if row is not None:
                return self._hydrate_paper(row)
        row = self.conn.execute(
            "SELECT * FROM papers WHERE paper_id = ? OR openalex_id = ? OR title = ?",
            (identifier, identifier, identifier),
        ).fetchone()
        if row is not None:
            return self._hydrate_paper(row)
        return None

    def _paper_brief(self, paper: dict[str, Any], note: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "paper_id": paper["paper_id"],
            "openalex_id": paper["openalex_id"],
            "resolved_doi": paper.get("resolved_doi"),
            "doi_uri": paper["doi_uri"],
            "title": paper["title"],
            "official_year": paper["official_year"],
            "journal": paper["journal"],
            "volume": paper["volume"],
            "issue": paper["issue"],
            "authors": paper.get("authors") or [],
            "pdf_snapshot_path": paper["pdf_snapshot_path"],
            "one_line_summary": (note or {}).get("one_line_summary"),
            "research_question": (note or {}).get("research_question"),
        }

    def search_papers(
        self,
        query: str,
        top_k: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[dict[str, Any]]:
        direct = self.resolve_paper(query)
        if direct:
            note = self.get_note(direct["openalex_id"])
            return [self._paper_brief(direct, note)]

        match_query = quote_fts_query(query)
        if not match_query:
            return []

        sql = """
            SELECT
                p.paper_id,
                p.openalex_id,
                p.resolved_doi,
                p.doi_uri,
                p.title,
                p.official_year,
                p.journal,
                p.volume,
                p.issue,
                p.authors_json,
                p.pdf_snapshot_path,
                n.one_line_summary,
                n.research_question,
                CASE WHEN lower(p.title) LIKE '%' || lower(?) || '%' THEN 0 ELSE 1 END AS title_match_rank,
                bm25(paper_search, 0.0, 12.0, 8.0, 1.0, 3.0, 3.0, 3.0, 2.0, 2.0, 1.5, 1.5, 1.5, 1.5) AS score
            FROM paper_search
            JOIN papers p ON p.openalex_id = paper_search.openalex_id
            LEFT JOIN paper_notes n ON n.openalex_id = p.openalex_id
            WHERE paper_search MATCH ?
        """
        params: list[Any] = [query, match_query]
        if year_from is not None:
            sql += " AND p.official_year >= ?"
            params.append(year_from)
        if year_to is not None:
            sql += " AND p.official_year <= ?"
            params.append(year_to)
        sql += " ORDER BY title_match_rank, score LIMIT ?"
        params.append(top_k)
        rows = self.conn.execute(sql, params).fetchall()
        if rows:
            results = []
            for row in rows:
                payload = dict(row)
                payload["authors"] = self._parse_json_field(payload.get("authors_json")) or []
                payload.pop("authors_json", None)
                results.append(payload)
            return results

        # Fallback for author-name queries even if FTS ranking does not surface them cleanly.
        author_rows = self.conn.execute(
            """
            SELECT DISTINCT
                p.paper_id,
                p.openalex_id,
                p.resolved_doi,
                p.doi_uri,
                p.title,
                p.official_year,
                p.journal,
                p.volume,
                p.issue,
                p.authors_json,
                p.pdf_snapshot_path,
                n.one_line_summary,
                n.research_question,
                CASE
                    WHEN lower(a.author_name) = lower(?) THEN 0
                    WHEN lower(a.author_name) LIKE lower(?) THEN 1
                    ELSE 2
                END AS author_match_rank
            FROM author_index a
            JOIN papers p ON p.openalex_id = a.openalex_id
            LEFT JOIN paper_notes n ON n.openalex_id = p.openalex_id
            WHERE lower(a.author_name) LIKE lower(?)
            ORDER BY author_match_rank, p.official_year DESC, p.title
            LIMIT ?
            """,
            (query, f"{query}%", f"%{query}%", top_k),
        ).fetchall()
        results = []
        for row in author_rows:
            payload = dict(row)
            payload["authors"] = self._parse_json_field(payload.get("authors_json")) or []
            payload.pop("authors_json", None)
            results.append(payload)
        return results

    def search_authors(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        query_norm = normalize_text(query)
        if not query_norm:
            return []
        rows = self.conn.execute(
            """
            SELECT
                author_name,
                COUNT(*) AS paper_count,
                MIN(official_year) AS first_year,
                MAX(official_year) AS last_year,
                SUM(CASE WHEN author_name_norm = ? THEN 1 ELSE 0 END) AS exact_match_hits,
                SUM(CASE WHEN author_name_norm LIKE ? THEN 1 ELSE 0 END) AS prefix_match_hits
            FROM author_index
            WHERE author_name_norm LIKE ?
            GROUP BY author_name
            ORDER BY exact_match_hits DESC, prefix_match_hits DESC, paper_count DESC, author_name
            LIMIT ?
            """,
            (query_norm, f"{query_norm}%", f"%{query_norm}%", top_k),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_author(self, identifier: str, top_k: int = 20) -> dict[str, Any] | None:
        query_norm = normalize_text(identifier)
        if not query_norm:
            return None
        exact_rows = self.conn.execute(
            """
            SELECT author_name
            FROM author_index
            WHERE author_name_norm = ?
            GROUP BY author_name
            ORDER BY COUNT(*) DESC, author_name
            LIMIT 1
            """,
            (query_norm,),
        ).fetchall()
        if exact_rows:
            author_name = exact_rows[0]["author_name"]
        else:
            matches = self.search_authors(identifier, top_k=1)
            if not matches:
                return None
            author_name = matches[0]["author_name"]

        count_row = self.conn.execute(
            "SELECT COUNT(*) AS paper_count, MIN(official_year) AS first_year, MAX(official_year) AS last_year FROM author_index WHERE author_name = ?",
            (author_name,),
        ).fetchone()
        paper_rows = self.conn.execute(
            """
            SELECT p.*
            FROM author_index a
            JOIN papers p ON p.openalex_id = a.openalex_id
            WHERE a.author_name = ?
            ORDER BY p.official_year DESC, p.title
            LIMIT ?
            """,
            (author_name, top_k),
        ).fetchall()
        note_rows = {
            row["openalex_id"]: row
            for row in self.conn.execute(
                """
                SELECT n.*
                FROM author_index a
                JOIN paper_notes n ON n.openalex_id = a.openalex_id
                WHERE a.author_name = ?
                """,
                (author_name,),
            ).fetchall()
        }
        papers = [
            self._paper_brief(
                self._hydrate_paper(row),
                self._hydrate_note(note_rows.get(row["openalex_id"])),
            )
            for row in paper_rows
        ]
        return {
            "query": identifier,
            "author_name": author_name,
            "paper_count": count_row["paper_count"],
            "first_year": count_row["first_year"],
            "last_year": count_row["last_year"],
            "papers": papers,
        }

    def get_note(self, identifier: str) -> dict[str, Any] | None:
        paper = self.resolve_paper(identifier)
        if not paper:
            return None
        row = self.conn.execute("SELECT * FROM paper_notes WHERE openalex_id = ?", (paper["openalex_id"],)).fetchone()
        return self._hydrate_note(row)

    def get_paper(self, identifier: str) -> dict[str, Any] | None:
        paper = self.resolve_paper(identifier)
        if not paper:
            return None
        note = self.get_note(paper["openalex_id"])
        counts = self.conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM raw_internal_citations WHERE citing_openalex_id = ?) AS raw_outgoing,
                (SELECT COUNT(*) FROM raw_internal_citations WHERE cited_openalex_id = ?) AS raw_incoming,
                (SELECT COUNT(*) FROM citation_judgments WHERE citing_openalex_id = ?) AS judged_outgoing,
                (SELECT COUNT(*) FROM citation_judgments WHERE cited_openalex_id = ?) AS judged_incoming,
                (SELECT COUNT(*) FROM substantive_edges WHERE citing_openalex_id = ?) AS substantive_outgoing,
                (SELECT COUNT(*) FROM substantive_edges WHERE cited_openalex_id = ?) AS substantive_incoming
            """,
            (
                paper["openalex_id"],
                paper["openalex_id"],
                paper["openalex_id"],
                paper["openalex_id"],
                paper["openalex_id"],
                paper["openalex_id"],
            ),
        ).fetchone()
        return {
            "paper": paper,
            "note": note,
            "edge_counts": dict(counts),
        }

    def _fetch_pair_relation(self, citing_openalex_id: str, cited_openalex_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
                r.*,
                j.citation_substance,
                j.relation_type,
                j.relation_description,
                j.rationale,
                j.model,
                j.requested_reasoning_effort,
                j.returned_reasoning_effort,
                j.api_key_slot,
                j.input_tokens,
                j.output_tokens,
                j.total_tokens,
                j.judgment_path,
                j.raw_response_path
            FROM raw_internal_citations r
            LEFT JOIN citation_judgments j ON j.pair_id = r.pair_id
            WHERE r.citing_openalex_id = ? AND r.cited_openalex_id = ?
            """,
            (citing_openalex_id, cited_openalex_id),
        ).fetchone()
        return self._hydrate_edge(row)

    def get_relation(self, source_identifier: str, target_identifier: str) -> dict[str, Any] | None:
        source_paper = self.resolve_paper(source_identifier)
        target_paper = self.resolve_paper(target_identifier)
        if not source_paper or not target_paper:
            return None

        source_note = self.get_note(source_paper["openalex_id"])
        target_note = self.get_note(target_paper["openalex_id"])
        direct = self._fetch_pair_relation(source_paper["openalex_id"], target_paper["openalex_id"])
        reverse = self._fetch_pair_relation(target_paper["openalex_id"], source_paper["openalex_id"])
        return {
            "source_paper": self._paper_brief(source_paper, source_note),
            "target_paper": self._paper_brief(target_paper, target_note),
            "direct": direct,
            "reverse": reverse,
        }

    def get_neighbors(
        self,
        identifier: str,
        mode: str = "substantive",
        direction: str = "both",
        top_k: int = 20,
        relation_type: str | None = None,
    ) -> dict[str, Any] | None:
        paper = self.resolve_paper(identifier)
        if not paper:
            return None
        if mode not in {"substantive", "all"}:
            raise ValueError("mode must be 'substantive' or 'all'")
        if direction not in {"both", "out", "in"}:
            raise ValueError("direction must be 'both', 'out', or 'in'")
        if relation_type and mode != "substantive":
            raise ValueError("relation_type can only be used when mode='substantive'")

        table = "substantive_edges" if mode == "substantive" else "raw_internal_citations"
        where_clauses = []
        params: list[Any] = []
        if direction in {"both", "out"}:
            where_clauses.append("e.citing_openalex_id = ?")
            params.append(paper["openalex_id"])
        if direction in {"both", "in"}:
            where_clauses.append("e.cited_openalex_id = ?")
            params.append(paper["openalex_id"])
        if relation_type:
            where_clauses = [f"({clause})" for clause in where_clauses]
            where_clauses.append("e.relation_type = ?")
            params.append(relation_type)

        sql = f"""
            SELECT
                e.*,
                p.paper_id AS neighbor_paper_id,
                p.openalex_id AS neighbor_openalex_id,
                p.resolved_doi AS neighbor_resolved_doi,
                p.doi_uri AS neighbor_doi_uri,
                p.title AS neighbor_title,
                p.official_year AS neighbor_official_year,
                p.authors_json AS neighbor_authors_json,
                p.pdf_snapshot_path AS neighbor_pdf_snapshot_path,
                n.one_line_summary AS neighbor_one_line_summary
            FROM {table} e
            JOIN papers p
                ON p.openalex_id = CASE
                    WHEN e.citing_openalex_id = ? THEN e.cited_openalex_id
                    ELSE e.citing_openalex_id
                END
            LEFT JOIN paper_notes n ON n.openalex_id = p.openalex_id
            WHERE {' OR '.join(where_clauses)}
            ORDER BY
                CASE WHEN e.citing_openalex_id = ? THEN 0 ELSE 1 END,
                e.pair_id
            LIMIT ?
        """
        sql_params = [paper["openalex_id"], *params, paper["openalex_id"], top_k]
        rows = self.conn.execute(sql, sql_params).fetchall()
        neighbors = []
        for row in rows:
            payload = self._hydrate_edge(row)
            payload["neighbor_authors"] = self._parse_json_field(payload.get("neighbor_authors_json")) or []
            payload.pop("neighbor_authors_json", None)
            neighbors.append(payload)
        return {
            "paper": self._paper_brief(paper, self.get_note(paper["openalex_id"])),
            "mode": mode,
            "direction": direction,
            "relation_type": relation_type,
            "neighbors": neighbors,
        }

    def get_subgraph(
        self,
        seed_ids: list[str],
        mode: str = "substantive",
        hops: int = 1,
        limit_nodes: int = 100,
    ) -> dict[str, Any]:
        if mode not in {"substantive", "all"}:
            raise ValueError("mode must be 'substantive' or 'all'")
        if hops < 1:
            raise ValueError("hops must be >= 1")
        table = "substantive_edges" if mode == "substantive" else "raw_internal_citations"

        seed_papers = [self.resolve_paper(seed_id) for seed_id in seed_ids]
        seed_papers = [paper for paper in seed_papers if paper is not None]
        visited = {paper["openalex_id"] for paper in seed_papers}
        frontier = set(visited)
        edges: dict[str, dict[str, Any]] = {}

        for _ in range(hops):
            if not frontier or len(visited) >= limit_nodes:
                break
            placeholders = ",".join("?" for _ in frontier)
            sql = f"""
                SELECT * FROM {table}
                WHERE citing_openalex_id IN ({placeholders})
                   OR cited_openalex_id IN ({placeholders})
            """
            params = [*frontier, *frontier]
            rows = self.conn.execute(sql, params).fetchall()
            next_frontier: set[str] = set()
            for row in rows:
                payload = dict(row)
                edges[payload["pair_id"]] = payload
                for node_id in (payload["citing_openalex_id"], payload["cited_openalex_id"]):
                    if node_id not in visited and len(visited) < limit_nodes:
                        visited.add(node_id)
                        next_frontier.add(node_id)
            frontier = next_frontier

        if not visited:
            return {"mode": mode, "hops": hops, "nodes": [], "edges": []}

        placeholders = ",".join("?" for _ in visited)
        paper_rows = self.conn.execute(
            f"SELECT * FROM papers WHERE openalex_id IN ({placeholders}) ORDER BY official_year, title",
            list(visited),
        ).fetchall()
        note_rows = {
            row["openalex_id"]: row
            for row in self.conn.execute(
                f"SELECT * FROM paper_notes WHERE openalex_id IN ({placeholders})",
                list(visited),
            ).fetchall()
        }
        nodes = [
            self._paper_brief(
                self._hydrate_paper(row),
                self._hydrate_note(note_rows.get(row["openalex_id"])),
            )
            for row in paper_rows
        ]
        filtered_edges = [
            self._hydrate_edge(edge)
            for edge in edges.values()
            if edge["citing_openalex_id"] in visited and edge["cited_openalex_id"] in visited
        ]
        filtered_edges.sort(key=lambda item: item["pair_id"])
        return {
            "mode": mode,
            "hops": hops,
            "seed_paper_ids": [paper["paper_id"] for paper in seed_papers],
            "seed_openalex_ids": [paper["openalex_id"] for paper in seed_papers],
            "nodes": nodes,
            "edges": filtered_edges,
        }
