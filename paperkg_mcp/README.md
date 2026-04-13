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

## Tool Semantics

### `search_papers`

Primary entry point for:

- paper titles
- DOIs
- topic phrases
- broad keyword search
- author-name fallback queries

Returned fields include:

- paper identity
- bibliographic metadata
- one-line note summary
- research question

### `search_authors`

Use this when the user starts from an author name and you want candidate author matches before retrieving papers.

Returned fields include:

- normalized author match
- paper count in the current corpus
- first and last year in the corpus

### `get_author`

Use this for author-level exploration.

Returned fields include:

- canonical matched author name
- paper count
- first and last year
- paper list with short note fields

### `get_paper`

Use this when the seed is a known paper.

Returned fields include:

- paper metadata
- structured paper note
- edge counts at three levels:
  - raw internal citation counts
  - judged citation counts
  - substantive edge counts

### `get_neighbors`

Main local graph-inspection tool.

Parameters:

- `mode="substantive"` for judged substantive edges
- `mode="all"` for raw internal citation links
- `direction="in" | "out" | "both"`
- optional `relation_type` filter in substantive mode

Returned fields include:

- the seed paper
- neighbor paper metadata
- edge explanation fields when available
- raw matched reference evidence

### `get_relation`

Direct pair-level lookup between two papers.

Returned fields include:

- source paper brief
- target paper brief
- direct edge from source to target when present
- reverse edge when present

This is the best tool for questions of the form:

- “What is the relationship between these two papers?”
- “Did paper A build on paper B?”

### `get_subgraph`

Local multi-paper graph expansion around one or more seed papers.

Parameters:

- `seed_identifiers`
- `mode`
- `hops`
- `limit_nodes`

Returned fields include:

- seed IDs
- local node set
- local edge set

## Recommended Entry Logic

- Start with `search_papers` for paper/title/topic questions.
- Start with `search_authors` or `get_author` for author questions.
- Use `get_relation` for pairwise citation questions.
- Use `get_neighbors` for 1-hop local inspection.
- Use `get_subgraph` for 2-hop local structure or branch tracing.
