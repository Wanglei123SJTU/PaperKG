# PaperKG MCP

This MCP server exposes the current JMR PaperKG base as a read-only tool layer.

Current default artifact:

- SQLite store: `data/jmr_2000_2025/paperkg_base/paperkg.sqlite`

Current build summary:

- `1497` papers
- `1497` paper notes
- `4593` raw internal citation pairs
- `4341` judged citation pairs
- `1868` substantive edges

Built from:

- `data/jmr_2000_2025/crossref_references/paper_summary.csv`
- `data/jmr_2000_2025/paper_notes/runs/ai02_full_notes_conc80/notes/`
- `data/jmr_2000_2025/citation_triage/manifest.csv`
- `data/jmr_2000_2025/citation_judgments/runs/ai02_full_judgments_one_pdf_note_three_keys_conc240/summary.csv`

Judgment workflow used in the current build:

- Stage 1: cheap triage on `note + metadata + raw matched reference`
- Stage 2: final relation judgment on `citing PDF + cited paper note`

## Build the SQLite store

```powershell
D:\Anaconda3\python.exe scripts\build_paperkg_sqlite.py
```

## Run the MCP server over stdio

```powershell
$env:PAPERKG_DB_PATH = (Resolve-Path "data/jmr_2000_2025/paperkg_base/paperkg.sqlite")
D:\Anaconda3\python.exe -m paperkg_mcp.server
```

## Tools

- `search_papers`
- `search_authors`
- `get_author`
- `get_paper`
- `get_neighbors`
- `get_relation`
- `get_subgraph`

Current notes:

- `search_papers` now supports title, DOI, author, and note-text queries.
- `get_neighbors` supports an optional `relation_type` filter in `substantive` mode.
- `get_relation` returns the direct citation record between two papers, including both directions when present.
