# Contributing

## Scope

This repository tracks the current working `PaperKG` pipeline for the `JMR 2000-2025` corpus.

Please keep contributions focused on:

- pipeline logic
- prompts and schemas
- MCP behavior
- data-processing scripts
- reproducibility and documentation

## Before You Start

- Do not commit publisher PDFs.
- Do not commit API keys, tokens, or local credential files.
- Keep large raw provider payloads out of Git unless they are intentionally part of the tracked outputs.
- Preserve the current `data/jmr_2000_2025` structure unless there is a deliberate migration.

## Local Data

The PDF corpus is shared outside GitHub:

- Google Drive: <https://drive.google.com/drive/folders/1NwP3bCY7hx_BmHgJYYNqbMl16uPrBuvX?usp=drive_link>

Place the PDF folders under:

- `data/jmr_2000_2025/pdfs/`

## Typical Workflow

1. Update prompts, schemas, or scripts.
2. Re-run the relevant pipeline stage.
3. Rebuild SQLite if the graph outputs changed.
4. Check that MCP still works against the rebuilt database.
5. Commit code and only the intended tracked artifacts.

## Minimal Commands

Build SQLite:

```powershell
D:\Anaconda3\python.exe scripts\build_paperkg_sqlite.py
```

Run MCP:

```powershell
$env:PAPERKG_DB_PATH = (Resolve-Path "data/jmr_2000_2025/paperkg_base/paperkg.sqlite")
D:\Anaconda3\python.exe -m paperkg_mcp.server
```

## Pull Requests

Prefer small, reviewable changes.

If a change affects graph contents, document:

- what input changed
- what output changed
- whether counts changed
- whether the SQLite artifact was rebuilt
