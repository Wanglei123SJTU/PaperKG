# PaperKG Final

This repository contains the current working version of a local `PaperKG` pipeline for the *Journal of Marketing Research* (`JMR`) corpus covering `2000-2025`.

The current project goal is not generic paper search. It is to build a **local, auditable internal citation graph** over JMR papers and expose it through a lightweight MCP server for relation-centric queries.

## Current Scope

- Corpus: local JMR PDF corpus, `2000-2025`
- Papers currently kept in the clean corpus: `1497`
- Reference source: `Crossref`
- Internal matched citation pairs: `4593`
- Final judged citation pairs: `4341`
- Final `substantive` edges: `1868`

Current SQLite artifact:

- [paperkg.sqlite](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\paperkg_base\paperkg.sqlite)

Current build manifest:

- [paperkg.manifest.json](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\paperkg_base\paperkg.manifest.json)

## Why The PDFs Are Not Meant For GitHub

The PDF corpus is large and should not be stored in the GitHub repository.

Reasons:

- Size: the local `pdfs/` directory is about `1.07 GB`
- Repository hygiene: PDFs dominate the repo and make collaboration harder
- Copyright risk: these are publisher PDFs, so a public GitHub repo is the wrong distribution channel

Current shared PDF location:

- Google Drive: <https://drive.google.com/drive/folders/1NwP3bCY7hx_BmHgJYYNqbMl16uPrBuvX?usp=drive_link>

Recommended sharing model:

- GitHub stores code, prompts, schemas, manifests, SQLite, and lightweight derived artifacts
- Google Drive stores the PDF corpus

## Current Pipeline

The current version runs in seven stages.

### 1. Local PDF Corpus

The project now uses a local JMR PDF corpus for `2000-2025`.

PDF root:

- [pdfs](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\pdfs)

This is the only paper source used for the current graph.

### 2. Crossref Reference Retrieval

For each paper in the corpus, the project queries `Crossref` and retrieves the article-level reference list.

Main outputs:

- [paper_summary.csv](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\crossref_references\paper_summary.csv)
- [references.csv](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\crossref_references\references.csv)

This step gives the raw bibliography layer.

### 3. Internal Reference Matching

The Crossref references are then matched back to the local `2000-2025` JMR corpus.

Main outputs:

- [internal_edges.csv](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\internal_reference_matches\internal_edges.csv)
- [matched_references.csv](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\internal_reference_matches\matched_references.csv)
- [summary.json](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\internal_reference_matches\summary.json)

This produces the `4593` raw internal citation pairs.

### 4. Paper Notes

Each paper is summarized into a structured note using the full PDF.

The note schema contains fields such as:

- `one_line_summary`
- `research_question`
- `research_gap`
- `focal_constructs`
- `context`
- `design_and_data`
- `main_findings`
- `claimed_contribution`
- `relation_to_prior_work`

Main prompt and schema:

- [paper_note_v1.md](C:\Users\27497\Desktop\PaperKG_Final\prompts\paper_note_v1.md)
- [paper_note_v1.schema.json](C:\Users\27497\Desktop\PaperKG_Final\schemas\paper_note_v1.schema.json)

Main outputs:

- [ai02_full_notes_conc80](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\paper_notes\runs\ai02_full_notes_conc80)

This run completed `1497/1497`.

### 5. Cheap Triage

The project does **not** send every internal citation pair directly to the expensive final relation judgment stage.

Instead, it first runs a cheap triage step using:

- citing paper note
- cited paper note
- pair metadata
- raw matched reference evidence

The triage output is one of:

- `drop_obvious_mention_only`
- `keep_for_relation_judgment`
- `uncertain`

Prompt and schema:

- [citation_triage_v1.md](C:\Users\27497\Desktop\PaperKG_Final\prompts\citation_triage_v1.md)
- [citation_triage_v1.schema.json](C:\Users\27497\Desktop\PaperKG_Final\schemas\citation_triage_v1.schema.json)

Main outputs:

- [manifest.csv](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\citation_triage\manifest.csv)
- [ai02_full_triage_conc80](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\citation_triage\runs\ai02_full_triage_conc80)

Current full triage distribution:

- `keep_for_relation_judgment`: `2973`
- `uncertain`: `1368`
- `drop_obvious_mention_only`: `252`

### 6. Final Citation Judgment

The current final judgment stage does **not** use two full PDFs by default.

Current evidence setup:

- full `citing` PDF
- structured note for the `cited` paper
- pair metadata
- raw matched reference evidence

This design was chosen because the citation function is mainly determined by how the citing paper uses the cited paper, and this setup is much cheaper than a dual-PDF pipeline.

Output schema:

- `citation_substance`
- `relation_type`
- `relation_description`
- `rationale`

Current judgment prompt:

- [citation_judgment_v2_one_pdf_note.md](C:\Users\27497\Desktop\PaperKG_Final\prompts\citation_judgment_v2_one_pdf_note.md)

Legacy dual-PDF prompt kept for reference:

- [citation_judgment_v1.md](C:\Users\27497\Desktop\PaperKG_Final\prompts\citation_judgment_v1.md)

Schema:

- [citation_judgment_v1.schema.json](C:\Users\27497\Desktop\PaperKG_Final\schemas\citation_judgment_v1.schema.json)

Main outputs:

- [manifest.csv](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\citation_judgments\manifest.csv)
- [ai02_full_judgments_one_pdf_note_three_keys_conc240](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\citation_judgments\runs\ai02_full_judgments_one_pdf_note_three_keys_conc240)

Current full judgment distribution:

- `mention_only`: `2467`
- `substantive`: `1868`
- `ambiguous`: `6`

Current `substantive` relation-type distribution:

- `applies`: `527`
- `foundational_for`: `492`
- `extends`: `463`
- `other`: `205`
- `refines`: `137`
- `challenges`: `44`

### 7. SQLite Build And MCP

All current outputs are compiled into a single SQLite artifact.

Builder:

- [build_paperkg_sqlite.py](C:\Users\27497\Desktop\PaperKG_Final\scripts\build_paperkg_sqlite.py)

The SQLite database stores:

- `papers`
- `paper_notes`
- `raw_internal_citations`
- `citation_judgments`
- `substantive_edges`
- `paper_search` (FTS5)

The MCP server is a thin read-only layer over this SQLite database.

Server:

- [server.py](C:\Users\27497\Desktop\PaperKG_Final\paperkg_mcp\server.py)

Store:

- [store.py](C:\Users\27497\Desktop\PaperKG_Final\paperkg_mcp\store.py)

Current MCP tools:

- `search_papers`
- `get_paper`
- `get_neighbors`
- `get_subgraph`

## How To Rebuild The Current Base

### Minimal Python dependencies

This repository currently assumes a Python environment with at least:

- `openai`
- `requests`
- `jsonschema`
- `mcp`

### Rebuild the SQLite store

```powershell
D:\Anaconda3\python.exe scripts\build_paperkg_sqlite.py
```

### Run the MCP server

```powershell
$env:PAPERKG_DB_PATH = "C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025\paperkg_base\paperkg.sqlite"
D:\Anaconda3\python.exe -m paperkg_mcp.server
```

## Repository Layout

Main code and configuration:

- [scripts](C:\Users\27497\Desktop\PaperKG_Final\scripts)
- [prompts](C:\Users\27497\Desktop\PaperKG_Final\prompts)
- [schemas](C:\Users\27497\Desktop\PaperKG_Final\schemas)
- [paperkg_mcp](C:\Users\27497\Desktop\PaperKG_Final\paperkg_mcp)

Main data root:

- [jmr_2000_2025](C:\Users\27497\Desktop\PaperKG_Final\data\jmr_2000_2025)

## Recommended GitHub Sharing Policy

Keep in GitHub:

- code
- prompts
- schemas
- SQLite artifact
- manifests
- paper note outputs
- triage outputs
- final citation judgment outputs
- concise summary CSV/JSON files

Do not keep in GitHub:

- publisher PDFs
- raw API response payload directories if repo size becomes annoying
- temporary caches
- local scratch files

For the PDF corpus, use the Google Drive folder above instead of GitHub.

## Current Collaboration State

This repository is now in a state where a collaborator can:

- inspect the current pipeline
- query the current graph through MCP
- audit paper notes
- audit triage outputs
- audit final citation judgments
- continue iterating on prompts, schemas, and graph logic

without needing the PDFs to live in the GitHub repository itself.
