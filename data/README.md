# Data Layout

This repository keeps lightweight derived artifacts for the current `JMR 2000-2025` build.

Main tracked subdirectories:

- `jmr_2000_2025/crossref_references`
- `jmr_2000_2025/internal_reference_matches`
- `jmr_2000_2025/paper_notes`
- `jmr_2000_2025/citation_triage`
- `jmr_2000_2025/citation_judgments`
- `jmr_2000_2025/paperkg_base`

The PDF corpus itself is not tracked in Git and should live at:

- `jmr_2000_2025/pdfs`

The shared PDF source is documented in the root [README](../README.md).

Notes:

- `paperkg_base/paperkg.sqlite` is the main consumable artifact for MCP.
- `paper_notes`, `citation_triage`, and `citation_judgments` contain the current tracked run outputs.
- Raw API response directories are intentionally excluded from Git.
