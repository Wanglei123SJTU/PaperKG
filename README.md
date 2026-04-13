# PaperKG

Local, auditable `PaperKG` for the *Journal of Marketing Research* (`JMR`) corpus, covering `2000-2025`.

The current system does one thing: build a **JMR-internal citation graph** that is explainable at both the paper level and the edge level, then expose it through a lightweight MCP server.

## Current Snapshot

- Corpus: `JMR 2000-2025`
- Papers in clean corpus: `1497`
- Reference source: `Crossref`
- Raw internal citation pairs: `4593`
- Final judged citation pairs: `4341`
- Final `substantive` edges: `1868`

Core artifact:

- [paperkg.sqlite](data/jmr_2000_2025/paperkg_base/paperkg.sqlite)

Build manifest:

- [paperkg.manifest.json](data/jmr_2000_2025/paperkg_base/paperkg.manifest.json)

## Data Access

The PDF corpus is **not** stored in GitHub.

Reasons:

- size
- repository hygiene
- publisher PDF copyright risk

Shared PDF location:

- Google Drive: <https://drive.google.com/drive/folders/1NwP3bCY7hx_BmHgJYYNqbMl16uPrBuvX?usp=drive_link>

To work locally with the full corpus, place the downloaded files under:

- [pdfs](data/jmr_2000_2025/pdfs)

Keep the year-based directory structure (`2000`, `2001`, ..., `2025`).

## Pipeline

### 1. PDF Corpus

The project starts from a local JMR PDF corpus for `2000-2025`.

### 2. Reference Retrieval

For each paper, the project retrieves article-level references from `Crossref`.

Outputs:

- [paper_summary.csv](data/jmr_2000_2025/crossref_references/paper_summary.csv)
- [references.csv](data/jmr_2000_2025/crossref_references/references.csv)

### 3. Internal Matching

Crossref references are matched back to the local JMR corpus to produce directed internal citation pairs.

Outputs:

- [internal_edges.csv](data/jmr_2000_2025/internal_reference_matches/internal_edges.csv)
- [matched_references.csv](data/jmr_2000_2025/internal_reference_matches/matched_references.csv)
- [summary.json](data/jmr_2000_2025/internal_reference_matches/summary.json)

### 4. Paper Notes

Each paper is converted into a structured note from the full PDF.

Main prompt and schema:

- [paper_note_v1.md](prompts/paper_note_v1.md)
- [paper_note_v1.schema.json](schemas/paper_note_v1.schema.json)

Main run:

- [ai02_full_notes_conc80](data/jmr_2000_2025/paper_notes/runs/ai02_full_notes_conc80)

### 5. Cheap Triage

Each internal citation pair first goes through a low-cost triage step using:

- citing paper note
- cited paper note
- pair metadata
- raw matched reference evidence

Labels:

- `drop_obvious_mention_only`
- `keep_for_relation_judgment`
- `uncertain`

Main prompt and schema:

- [citation_triage_v1.md](prompts/citation_triage_v1.md)
- [citation_triage_v1.schema.json](schemas/citation_triage_v1.schema.json)

Main run:

- [ai02_full_triage_conc80](data/jmr_2000_2025/citation_triage/runs/ai02_full_triage_conc80)

### 6. Final Citation Judgment

The final relation judgment uses:

- full `citing` PDF
- structured note for the `cited` paper
- pair metadata
- raw matched reference evidence

This is cheaper than a dual-PDF pipeline while still centering the actual citation use in the citing paper.

Output fields:

- `citation_substance`
- `relation_type`
- `relation_description`
- `rationale`

Current prompt and schema:

- [citation_judgment_v2_one_pdf_note.md](prompts/citation_judgment_v2_one_pdf_note.md)
- [citation_judgment_v1.schema.json](schemas/citation_judgment_v1.schema.json)

Main run:

- [ai02_full_judgments_one_pdf_note_three_keys_conc240](data/jmr_2000_2025/citation_judgments/runs/ai02_full_judgments_one_pdf_note_three_keys_conc240)

### 7. SQLite + MCP

All outputs are compiled into a single SQLite artifact and served through MCP.

Main code:

- [build_paperkg_sqlite.py](scripts/build_paperkg_sqlite.py)
- [server.py](paperkg_mcp/server.py)
- [store.py](paperkg_mcp/store.py)

MCP tools:

- `search_papers`
- `get_paper`
- `get_neighbors`
- `get_subgraph`

## Run Locally

Minimal Python dependencies:

- `openai`
- `requests`
- `jsonschema`
- `mcp`

Build SQLite:

```powershell
D:\Anaconda3\python.exe scripts\build_paperkg_sqlite.py
```

Run MCP:

```powershell
$env:PAPERKG_DB_PATH = (Resolve-Path "data/jmr_2000_2025/paperkg_base/paperkg.sqlite")
D:\Anaconda3\python.exe -m paperkg_mcp.server
```

## Repository Layout

Code and configuration:

- [scripts](scripts)
- [prompts](prompts)
- [schemas](schemas)
- [paperkg_mcp](paperkg_mcp)

Main data root:

- [jmr_2000_2025](data/jmr_2000_2025)

Collaboration guide:

- [CONTRIBUTING.md](CONTRIBUTING.md)

## Collaboration Status

This repository is already in a usable state for collaboration. A collaborator can:

- inspect the full pipeline
- review prompts and schemas
- audit paper notes
- audit triage outputs
- audit final citation judgments
- query the graph through MCP
- continue iterating on the graph construction logic

The only large external dependency is the PDF corpus, which stays on Google Drive rather than GitHub.
