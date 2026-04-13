# PaperKG MCP

`paperkg_mcp` exposes the current JMR `PaperKG` base as a read-only MCP server.

It should be treated as an optional local graph tool for JMR paper relationships, not as the only research interface for every question. The graph is especially useful for local citation structure, paper-to-paper relations, and author-level exploration inside the current corpus. For broader questions, sparse graph regions, or missing-coverage cases, notes, PDFs, and web research may still be better evidence sources.

## Current Default Artifact

Default SQLite database:

- `data/jmr_2000_2025/paperkg_base/paperkg.sqlite`

Current build summary:

- papers: `1497`
- paper notes: `1497`
- raw internal citation pairs: `4593`
- judged citation pairs: `4341`
- substantive edges: `1868`

## What Is Inside the Database

The SQLite build currently combines:

- paper-level metadata from the local `2000-2025` JMR corpus
- structured paper notes
- raw internal citation matches from Crossref reference retrieval
- cheap triage outputs
- final citation judgments
- the filtered `substantive` graph

This means the MCP layer can answer both:

- paper-level lookup questions
- edge-level relationship questions

## Build the SQLite Base

```powershell
D:\Anaconda3\python.exe scripts\build_paperkg_sqlite.py
```

## Run the MCP Server

```powershell
$env:PAPERKG_DB_PATH = (Resolve-Path "data/jmr_2000_2025/paperkg_base/paperkg.sqlite")
D:\Anaconda3\python.exe -m paperkg_mcp.server
```

If `PAPERKG_DB_PATH` is not set, the server falls back to the default local database path above.

## MCP Tools

The current server exposes seven practical entry points:

- `search_papers`
- `search_authors`
- `get_author`
- `get_paper`
- `get_neighbors`
- `get_relation`
- `get_subgraph`

## Tool Semantics

### `search_papers`

Use this when the input is a paper title, DOI, topic phrase, broad keyword query, or sometimes an author-like query.

It searches:

- DOI and paper identifiers
- exact and fuzzy title matches
- author names
- abstract text
- paper-note text

Best for:

- finding seed papers for a topic
- resolving a paper from noisy user input
- broad keyword-based paper discovery inside the current corpus

### `search_authors`

Use this when the input is an author name and you want candidate author matches first.

Best for:

- ambiguous or partial author-name queries
- checking whether an author is present in the current corpus

### `get_author`

Use this when you want all papers for one author inside the current JMR corpus.

Best for:

- author-level exploration
- checking corpus coverage for a specific author
- selecting representative papers before graph inspection

### `get_paper`

Returns one paper plus:

- core metadata
- structured paper note
- edge counts for raw, judged, and substantive layers

Best for:

- grounding a discussion in one paper
- checking whether a paper is structurally central or isolated

### `get_neighbors`

Returns 1-hop neighbors around a paper.

Supports:

- `mode="substantive"` for the judged graph
- `mode="all"` for raw internal citation pairs
- `direction="in" | "out" | "both"`
- optional `relation_type` filtering in substantive mode

Best for:

- direct follow-up papers
- direct predecessors
- local branch inspection

### `get_relation`

Returns the direct relationship between two papers when one exists in the current graph layers.

Best for:

- "How are these two papers related?"
- checking whether a direct substantive edge exists
- comparing direct judged relation versus raw citation linkage

### `get_subgraph`

Builds a local 1-hop or 2-hop graph around one or more seed papers.

Best for:

- local research-line inspection
- small branch summaries
- bridge-node or neighborhood analysis

## Recommended Entry Logic

- Author question  
  `search_authors` -> `get_author` -> `get_neighbors` / `get_subgraph`

- Specific paper question  
  `get_paper` -> `get_neighbors` / `get_relation`

- Topic question  
  `search_papers` -> choose 1-3 seed papers -> `get_neighbors` / `get_subgraph`

- Direct relation question  
  `get_paper` or `search_papers` -> `get_relation`

## Scope Reminder

This MCP server is strongest when the question is about:

- local JMR citation neighborhoods
- direct paper-to-paper relations
- local author lines
- interpretable 1-hop / 2-hop subgraphs

It is weaker when the question is about:

- complete field-level histories
- broad themes with sparse internal citation structure
- papers missing from the current local corpus
- topics better answered through direct note reading, PDF reading, or web search

In short: use the graph when it helps, but do not force the graph when another evidence source is better.
