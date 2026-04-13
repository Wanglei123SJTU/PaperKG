from __future__ import annotations

import os
import site
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / ".vendor"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
site.addsitedir(str(VENDOR_DIR))
PYWIN32_DLL_DIR = VENDOR_DIR / "pywin32_system32"
if PYWIN32_DLL_DIR.exists():
    os.environ["PATH"] = f"{PYWIN32_DLL_DIR}{os.pathsep}{os.environ.get('PATH', '')}"
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(PYWIN32_DLL_DIR))

from mcp.server import FastMCP  # noqa: E402

from paperkg_mcp.store import PaperKGStore  # noqa: E402


DEFAULT_DB_PATH = ROOT / "data" / "jmr_2000_2025" / "paperkg_base" / "paperkg.sqlite"
DB_PATH = Path(os.environ.get("PAPERKG_DB_PATH", DEFAULT_DB_PATH))

mcp = FastMCP("paperkg-jmr")
store = PaperKGStore(DB_PATH)


@mcp.tool()
def search_papers(query: str, top_k: int = 10, year_from: int | None = None, year_to: int | None = None) -> dict:
    """Search JMR papers by title, DOI, author, and paper-note text."""
    return {
        "query": query,
        "top_k": top_k,
        "year_from": year_from,
        "year_to": year_to,
        "results": store.search_papers(query=query, top_k=top_k, year_from=year_from, year_to=year_to),
    }


@mcp.tool()
def search_authors(query: str, top_k: int = 10) -> dict:
    """Search authors represented in the current JMR PaperKG corpus."""
    return {
        "query": query,
        "top_k": top_k,
        "results": store.search_authors(query=query, top_k=top_k),
    }


@mcp.tool()
def get_author(identifier: str, top_k: int = 20) -> dict:
    """Fetch one author plus their papers in the current JMR PaperKG corpus."""
    result = store.get_author(identifier=identifier, top_k=top_k)
    if result is None:
        return {"found": False, "identifier": identifier}
    return {"found": True, "identifier": identifier, **result}


@mcp.tool()
def get_paper(identifier: str) -> dict:
    """Fetch one paper plus its note and local paths by DOI, OpenAlex id, or exact title."""
    result = store.get_paper(identifier)
    if result is None:
        return {"found": False, "identifier": identifier}
    return {"found": True, "identifier": identifier, **result}


@mcp.tool()
def get_neighbors(
    identifier: str,
    mode: str = "substantive",
    direction: str = "both",
    top_k: int = 20,
    relation_type: str | None = None,
) -> dict:
    """Fetch incoming/outgoing neighbors for a paper. Default mode uses substantive labeled edges."""
    result = store.get_neighbors(
        identifier=identifier,
        mode=mode,
        direction=direction,
        top_k=top_k,
        relation_type=relation_type,
    )
    if result is None:
        return {"found": False, "identifier": identifier}
    return {"found": True, "identifier": identifier, **result}


@mcp.tool()
def get_relation(source_identifier: str, target_identifier: str) -> dict:
    """Fetch the direct citation relation between two papers in both directions when present."""
    result = store.get_relation(source_identifier=source_identifier, target_identifier=target_identifier)
    if result is None:
        return {
            "found": False,
            "source_identifier": source_identifier,
            "target_identifier": target_identifier,
        }
    return {
        "found": True,
        "source_identifier": source_identifier,
        "target_identifier": target_identifier,
        **result,
    }


@mcp.tool()
def get_subgraph(seed_identifiers: list[str], mode: str = "substantive", hops: int = 1, limit_nodes: int = 100) -> dict:
    """Fetch a local citation subgraph around one or more seed papers."""
    return store.get_subgraph(seed_ids=seed_identifiers, mode=mode, hops=hops, limit_nodes=limit_nodes)


if __name__ == "__main__":
    mcp.run()
