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

To work locally with the full corpus, place the downloaded files under `data/jmr_2000_2025/pdfs/` and keep the year-based directory structure (`2000`, `2001`, ..., `2025`).

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

The MCP layer is an optional research tool, not a mandatory workflow. It is most useful for local JMR citation-relationship questions, author-level retrieval inside the current corpus, and local graph inspection. It should not be treated as the only evidence source for every research question.

Main code:

- [build_paperkg_sqlite.py](scripts/build_paperkg_sqlite.py)
- [server.py](paperkg_mcp/server.py)
- [store.py](paperkg_mcp/store.py)

MCP tools:

- `search_papers`
- `search_authors`
- `get_author`
- `get_paper`
- `get_neighbors`
- `get_relation`
- `get_subgraph`

### MCP Entry Points

The MCP layer currently has seven practical entry points. These are optional tool entry points, not a mandatory workflow for every research question.

- `search_papers`
  Use this when the input is a paper title, DOI, topic phrase, or a broad keyword query. It searches title, DOI, author names, abstract text, and paper-note text.

- `search_authors`
  Use this when the input is an author name and you want candidate author matches first.

- `get_author`
  Use this when you want the papers for one author in the current JMR corpus. This is the best entry point for author-level exploration.

- `get_paper`
  Use this when you already know a specific paper and want its metadata, note, and edge counts.

- `get_neighbors`
  Use this for 1-hop graph inspection around a paper. This is the main local-graph tool. It supports:
  - `mode="substantive"` for the judged graph
  - `mode="all"` for raw internal citation pairs
  - `direction="in" | "out" | "both"`
  - optional `relation_type` filtering in substantive mode

- `get_relation`
  Use this when the question is specifically about the direct relationship between two papers. It returns the direct judged edge when present, plus the reverse direction if that also exists.

- `get_subgraph`
  Use this when you want a 1-hop or 2-hop local citation graph around one or more seed papers.

### Typical MCP Workflows

- Author question
  `search_authors` -> `get_author` -> `get_neighbors` / `get_subgraph`

- Paper relationship question
  `get_paper` -> `get_relation` -> `get_neighbors`

- Topic question
  `search_papers` -> choose 1-3 seed papers -> `get_neighbors` / `get_subgraph`

- Reading-line question
  `get_paper` -> `get_neighbors(mode="substantive")` -> `get_subgraph(hops=2)`

## Example: Real MCP-Backed Query

Example user input:

> What does the V. Kumar research line look like in the current JMR PaperKG?

Representative MCP workflow:

> `search_authors("V. Kumar")` -> `get_author("V. Kumar")` -> inspect representative papers with `get_neighbors(...)` and `get_subgraph(...)`

Representative MCP-backed answer:

> Based on the current substantive JMR PaperKG, V. Kumar looks less like one long self-citation chain and more like three internal clusters plus several outward-facing, method-heavy branches. In the current corpus he has `19` JMR papers (`2000-2019`), but only `7` substantive edges are directly `V. Kumar -> V. Kumar`, so the line is not densely self-contained. Using three representative seeds (`Repeat Churn` `2018`, `Dynamically Managing...` `2017`, `Influencing Acquisition Performance` `2017`), the local `2-hop substantive subgraph` is `58` nodes / `64` edges, which is dense enough to summarize meaningfully.
>
> Relationship-state / permission marketing / email is the clearest internal branch. `Recovering Hidden Buyer-Seller Relationship States` (`2013`) feeds into `Dynamically Managing a Profitable Email Marketing Program` (`2017`), and `The Relative Influence of Economic and Relational Direct Marketing Communications...` (`2018`) explicitly refines that `2013` line. `Modeling Customer Opt-In and Opt-Out...` (`2014`) also sits inside this branch and is extended by the `2017` email paper.
>
> Customer profits / CLV / cash-flow is a second clear branch. `Managing Customer Profits` (`2014`) is later applied by `Measuring the Lifetime Value of a Customer in the Consumer Packaged Goods Industry` (`2016`) and extended by `Linking Customer Behaviors to Cash Flow Level and Volatility` (`2017`). Upstream, `Optimal Customer Relationship Management Using Bayesian Decision Theory` (`2007`) acts as a `foundational_for` node for the `2016` CLV paper.
>
> Sales-force value is a smaller but coherent branch. `Measuring and Managing a Salesperson's Future Value to the Firm` (`2014`) is extended by `Why Do Salespeople Quit?` (`2017`), and later non-V. Kumar papers in `2019` and `2022` keep extending that line.
>
> Several important V. Kumar papers are more outward-facing than internally linked. `Are you Back for Good or Still Shopping Around?` (`2018`) extends `Recapturing Lost Customers` (`2004`); `Influencing Acquisition Performance...` (`2017`) extends `Why Some Acquisitions Do Better Than Others` (`2007`) and refines `Ties that Bind` (`2010`); `Modeling Emerging-Market Firms' Competitive Retail Distribution Strategies` (`2019`) is strongly method-driven rather than anchored to earlier V. Kumar papers.
>
> The strongest cross-branch pattern is methodological reuse. Seven different V. Kumar papers substantively apply `A Control Function Approach to Endogeneity in Consumer Choice Models` (`2010`), so the graph shows a recurring JMR-methods spine running through otherwise different substantive areas.
>
> My inference from the graph is that V. Kumar is best represented here as a portfolio of local branches around CRM / relationship-state modeling, customer profitability / CLV, and sales-force value, with repeated borrowing from JMR methods papers rather than a single narrow citation lineage. Coverage caveat: this is only the current internal JMR PaperKG, so influence outside JMR or outside current graph coverage will not show up here.

This example reflects the current system's strength: it can already produce useful local author-line answers when the underlying substantive graph is dense enough.

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
