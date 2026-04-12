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
                p.pdf_snapshot_path,
                n.one_line_summary,
                n.research_question,
                CASE WHEN lower(p.title) LIKE '%' || lower(?) || '%' THEN 0 ELSE 1 END AS title_match_rank,
                bm25(paper_search, 10.0, 8.0, 1.0, 3.0, 3.0, 3.0, 2.0, 2.0, 1.5, 1.5, 1.5, 1.5) AS score
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
        return [dict(row) for row in rows]

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
                (SELECT COUNT(*) FROM substantive_edges WHERE citing_openalex_id = ?) AS substantive_outgoing,
                (SELECT COUNT(*) FROM substantive_edges WHERE cited_openalex_id = ?) AS substantive_incoming
            """,
            (paper["openalex_id"], paper["openalex_id"], paper["openalex_id"], paper["openalex_id"]),
        ).fetchone()
        return {
            "paper": paper,
            "note": note,
            "edge_counts": dict(counts),
        }

    def get_neighbors(
        self,
        identifier: str,
        mode: str = "substantive",
        direction: str = "both",
        top_k: int = 20,
    ) -> dict[str, Any] | None:
        paper = self.resolve_paper(identifier)
        if not paper:
            return None
        if mode not in {"substantive", "all"}:
            raise ValueError("mode must be 'substantive' or 'all'")
        if direction not in {"both", "out", "in"}:
            raise ValueError("direction must be 'both', 'out', or 'in'")

        table = "substantive_edges" if mode == "substantive" else "raw_internal_citations"
        where_clauses = []
        params: list[Any] = []
        if direction in {"both", "out"}:
            where_clauses.append("e.citing_openalex_id = ?")
            params.append(paper["openalex_id"])
        if direction in {"both", "in"}:
            where_clauses.append("e.cited_openalex_id = ?")
            params.append(paper["openalex_id"])

        sql = f"""
            SELECT
                e.*,
                p.paper_id AS neighbor_paper_id,
                p.openalex_id AS neighbor_openalex_id,
                p.resolved_doi AS neighbor_resolved_doi,
                p.doi_uri AS neighbor_doi_uri,
                p.title AS neighbor_title,
                p.official_year AS neighbor_official_year,
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
        return {
            "paper": self._paper_brief(paper, self.get_note(paper["openalex_id"])),
            "mode": mode,
            "direction": direction,
            "neighbors": [dict(row) for row in rows],
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
        edges: dict[int, dict[str, Any]] = {}

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
            edge
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
