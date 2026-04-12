# PaperKG: Domain-Specific Academic Knowledge Graph for Agent Access

## Vision

A lightweight, distributable knowledge graph of academic papers in a specific domain (starting with quantitative marketing). The graph captures not just citation links but **semantic relationships** between papers — who extended whose model, who contradicted whose finding, who applied whose method to a new domain. Any LLM agent can access this graph to deeply understand a research area.

**Analogy:** GitNexus indexes a codebase into a KG so agents understand code structure. PaperKG indexes a research domain into a KG so agents understand intellectual structure.

---

## Why This Is Needed

**Existing tools (Connected Papers, Semantic Scholar, Elicit) show citations but don't explain relationships.**

A citation link "Nevo 2001 → BLP 1995" tells you nothing. The useful knowledge is: "Nevo 2001 provides a practitioner's guide to implementing BLP's random coefficients demand estimation, simplifying the GMM estimation procedure."

Researchers build this understanding manually by reading hundreds of papers. PaperKG precomputes it.

**The moat is not the technology (S2 API + LLM is replicable) -- it is the expert-curated corpus boundary, the verified relationship labels, and the domain-specific taxonomy that emerges from iterative expert review. These are human-judgment artifacts that compound in value over time.**

---

## Background Research

### Literature Landscape

Key papers informing this project (full survey archived in git history):

**GraphRAG family** — Microsoft GraphRAG (2024), LazyGraphRAG, LightRAG: established that KGs enhance retrieval for "global" questions requiring corpus-wide understanding. Key insight: community detection (Leiden) + LLM-generated summaries enables multi-resolution querying.

**Agent Memory + KG** — AriGraph (IJCAI'25), Zep/Graphiti (arXiv'25), Mem0 (arXiv'25), A-MEM (NeurIPS'25), MAGMA (arXiv'26): agents that build and query knowledge graphs as memory. Key insight from Mem0: graph-enhanced variant only ~2% better than vector-only, suggesting current graph integrations are superficial.

**Tool-Use KG** — Agent-as-a-Graph (arXiv'25), Graph-CoT (ACL'24): representing tool ecosystems as graphs for agent tool selection.

**KG Construction** — KARMA (NeurIPS'25 Spotlight): 9-agent architecture, 83.1% correctness on scientific KG enrichment. Graphusion (TheWebConf'25): zero-shot KG construction with fusion module.

**KG Reasoning** — SymAgent (WebConf'25), KG-R1 (arXiv'25): smaller models (3-7B) with structured KG reasoning competitive with much larger LLMs.

### KG Architecture: What Won

**Property graphs won over RDF for practical use.** Neo4j ranks ~#20 on DB-Engines; RDF systems like Jena TDB rank ~#102. The GQL ISO standard (April 2024) formalized property graph semantics, giving them the standards foundation they previously lacked vs SPARQL.

**Every agent-era project uses property graphs, none use RDF:**
- GraphRAG: custom property graph in Parquet files
- Graphiti/Zep: property graph in Neo4j with temporal extensions
- Mem0: directed labeled graph in Neo4j
- Cognee: flexible property graph (only project to optionally support RDF via RDFLib)
- GitNexus: code-specific property graph in KuzuDB
- MCP-KG: minimal entity-relation in JSONL

**RDF retains value** only where cross-organization interoperability, formal reasoning (OWL), or Linked Open Data publishing matter — none of which apply to our use case.

### How Popular Projects Actually Structure Their KGs

Analysis of 6 open-source projects' actual source code:

| Project | Storage | Node Schema | Edge Schema | Token Budgeting | LLM Serialization |
|---------|---------|-------------|-------------|-----------------|-------------------|
| MCP-KG (2k stars) | JSONL | 3 fields (name, type, observations) | 3 fields (from, to, relationType) | None | Pretty JSON |
| LlamaIndex KG | Python dict | Plain strings | (S, P, O) tuples | None (deprecated) | Directed path strings |
| GitNexus (17.6k) | KuzuDB (in-memory) | 20+ properties, 34 types | 6 fields, 15 types | None | Markdown tables |
| Cognee (14.3k) | Neo4j/Kuzu + Postgres | Generic + JSON bag | Generic + JSON bag | None | Pydantic objects |
| Graphiti (24k) | Neo4j | 5 typed node classes | EntityEdge: 10 fields + temporal validity (valid_at, invalid_at, expired_at) | None (app layer) | `fact` natural language field |
| **GraphRAG (31.6k)** | **Parquet** | 10 fields | 8 fields + communities | **Yes (explicit tokenizer)** | **Pipe-delimited tables** |

**Complexity spectrum:**
- Simple end: MCP-KG, LlamaIndex — flat triples, no schema enforcement
- Middle: GitNexus, Cognee — typed property graphs with flexible attribute bags
- Sophisticated: Graphiti (temporal validity), GraphRAG (hierarchical communities + token budgeting)

**Key architectural insights for our project:**
1. **Only GraphRAG implements proper token budgeting** — critical for agent context windows. We need this.
2. **Graphiti's `fact` field pattern** — storing natural language assertion alongside structured triple is the best approach for agent consumption. E.g., `fact: "Nevo 2001 provides a practitioner's guide to BLP's random coefficients model"` alongside `fine_type: "extends_model"`.
3. **Airbnb uses relational DB (not graph DB) for their KG** — one table for nodes, one for edges, each with a GUID. This validates our SQLite approach. No need for Neo4j at our scale.
4. **Wikidata's statement model** is instructive — statements have ranks (preferred/normal/deprecated) and qualifiers (context/conditions). Our confidence scores and expert_verified flags serve a similar purpose.

### Academic Paper KG Precedents

**NLP-AKG is the closest precedent to our project:**
- 620,353 entities, 2,271,584 relations from 60,826 ACL Anthology papers
- Neo4j storage
- **15 entity types**: Title, Author, Institution, Conference, Date, Field, Keywords, Problem, Method, Model, Task, Dataset, Metric, Result, Innovation
- **29 relation types** split into:
  - **Intra-paper** (within a paper): writes, works_for, publishes, belongs_to, keywords, solves, adopts, proposes, works_on, innovates, experiments_on, uses, faces, achieves
  - **Inter-paper** (between papers): `direct_use` (paper directly uses cited content), `task_related` (similar tasks)
- **Extraction quality: 0.94 accuracy for entities, 0.93 for inter-paper relations** (manual evaluation of 100 papers)
- **Method**: Few-shot LLM construction

**What NLP-AKG lacks (and we should add):**
- Temporal awareness (when did a method become standard?)
- Methodological lineage (who extended whose model?)
- Fine-grained inter-paper relationships (only 2 inter-paper types vs our proposed taxonomy)
- Agent-accessible interface (it's a static Neo4j dump)
- Token-budgeted context serialization

**Other academic KGs:**
- **OpenAlex**: 209M works, free API, but only hierarchical topic assignments — no semantic relationships between papers
- **SemOpenAlex**: 26B RDF triples, adds SPARQL reasoning, but still metadata-level (no content relationships)
- **MAKG (Microsoft)**: 8B RDF triples, 210M papers, discontinued 2021
- **CS-KG 2.0**: 24.7M entities, 179 relation types from 14.5M CS papers — closest in ambition but uses traditional NLP extraction (DyGIE++), not LLMs

**Gap our project fills:** No existing academic KG combines (1) LLM-based deep semantic relationship extraction, (2) agent-accessible interface with token budgeting, (3) domain-expert curation, and (4) lightweight distributable format.

### Competitive Analysis

| Tool | What it does | What PaperKG adds |
|------|-------------|-------------------|
| **Semantic Scholar** | Citation graph, basic intents, search | Fine-grained semantic relationships, domain-specific curation, offline agent access |
| **Connected Papers** | Visual citation graph for a single paper | Covers whole domain, not single-paper ego networks; adds relationship types |
| **Elicit** | LLM-powered literature search and extraction | Elicit is query-time (slow, costly); PaperKG is precomputed. Lacks graph structure |
| **ResearchRabbit** | Discovery via citation chains | No semantic relationship classification |
| **OpenAlex** | Comprehensive metadata, topic hierarchy | No content-level relationships between papers |
| **NLP-AKG** | Deep semantic KG for NLP papers | Only NLP domain; only 2 inter-paper relation types; no agent interface |

---

## Data Foundation: Semantic Scholar API

S2 API provides critical raw materials:

| S2 Field | What It Gives Us | How We Use It |
|----------|------------------|---------------|
| `contexts` | Citing sentences (the actual text where paper A mentions paper B) | Input to LLM for fine-grained relationship classification |
| `intents` | 3-class citation type (Background / Method / Result Extension) | Coarse-grained relationship — useful as features, but too coarse for our needs |
| `isInfluential` | Whether the citation is influential | Edge weighting |
| `abstract` | Paper abstract | Node content for search and LLM understanding |
| `tldr` | AI-generated summary | Compact paper representation |
| `embedding` | SPECTER vectors | Semantic similarity between papers |
| `venue` | Journal/conference | Filter to domain-specific papers |
| `openAccessPdf` | PDF link if available | Optional: deep reading for high-importance papers |

**Key insight: S2 gives us citing sentences for free.** These sentences are where authors explicitly state the relationship ("Building on X, we...", "Unlike Y, our approach...", "Following the identification strategy of Z..."). This is the richest signal for relationship extraction, and we don't need PDFs for it.

**When PDFs add value:**
- S2 citation contexts are typically 1-2 sentences. For foundational papers with complex relationships, reading the full introduction/related work section gives richer understanding.
- Not all papers have citation contexts in S2 (requires full-text access on their end).
- Strategy: use S2 contexts where available (coverage may be 30-50% for marketing journals), abstract-only classification for the remainder, and PDF deep-read only for top-cited foundational papers (~50-100 papers).

### Two Ways to Get S2 Data

**Option A: Graph API (per-query) — best for Phase 0**
- REST endpoints: `/paper/search`, `/paper/batch`, `/paper/{id}/citations`, etc.
- Rate limit: 1 req/sec with API key; free tier shares 1000 req/sec pool across all unauthenticated users
- Good for small samples (~100 papers); total ~5,000 calls for full corpus (~1.5 hours at 1 req/sec)

**Option B: Datasets API (bulk download) — best for full corpus construction**
- Downloads the entire S2 academic graph as compressed JSON files
- Available datasets: `papers`, `abstracts`, `citations` (includes contexts + intents), `embeddings` (SPECTER2), `tldrs`, `authors`, `paper-ids`
- Total S2 graph: 225M+ papers, 2.8B+ citation edges
- Process: download full dumps → local filter by venue to extract marketing papers
- Requires API key; no rate limit concerns since it is a file download
- Trade-off: download size is large (potentially tens of GB compressed) but eliminates all rate limit issues

**Recommendation:**
- Phase 0: use Graph API with API key (~100 papers)
- Phase 1 full corpus: evaluate whether Graph API (~5,000 calls, ~1.5 hours) or Datasets API (large download, then local filter) is more practical. Graph API is simpler for ~2,500 papers; Datasets API is better if we need to do repeated corpus boundary adjustments.

### API Key & Rate Limiting

**API key**: stored in `.env` (gitignored), loaded via `os.getenv("S2_API_KEY")`. Pass as `x-api-key` header.

**Rate limit: strictly 1 request per second, cumulative across all endpoints.**

Implementation requirements:
1. **Hard rate limiter**: enforce minimum 1.0s between requests, no exceptions. Use `time.sleep()` or async equivalent to guarantee compliance.
2. **Exponential backoff on 429 (Too Many Requests)**:
   - Retry 1: wait 2s
   - Retry 2: wait 4s
   - Retry 3: wait 8s
   - Retry 4: wait 16s
   - Retry 5: wait 32s
   - After 5 retries: log error, skip this request, continue pipeline
   - Add jitter (random 0-0.5s) to each wait to avoid thundering herd
3. **Backoff on 5xx (Server Error)**: same strategy as 429
4. **Log every request**: timestamp, endpoint, status code, response time. This creates an audit trail and helps debug rate limit issues.
5. **Graceful resume**: persist progress (which papers have been fetched) so the pipeline can resume after interruption without re-fetching.
6. **Estimated time at 1 req/sec**:
   - Phase 0 (~200 requests): ~3-4 minutes
   - Full corpus (~5,000 requests): ~1.5 hours

### Fallback Data Sources

S2 is the best source because it uniquely provides citation contexts + intents + SPECTER embeddings. But if S2 has gaps:

| Data Source | Free | What It Provides | What It Lacks | When to Use |
|-------------|------|------------------|---------------|-------------|
| **Semantic Scholar** | Yes | Metadata, abstracts, citation contexts, intents, embeddings, TLDRs | Coverage gaps for non-open-access journals | Primary source |
| **OpenAlex** | Yes | Metadata, abstracts, citation lists, concepts | No citation contexts, no intents, no embeddings | Fill metadata gaps for papers S2 doesn't cover |
| **CrossRef** | Yes (no key) | DOI → metadata mapping, reference lists | No abstracts, no citation contexts | DOI resolution and cross-referencing |
| **Scopus** | Institutional | Most comprehensive metadata for social science journals | Requires university access, no citation contexts | Validate corpus completeness against Scopus counts |

Pipeline design: abstract the data source behind an interface so OpenAlex or CrossRef can substitute for metadata retrieval if S2 changes terms.

### PDF Strategy

**Do not batch-download all PDFs.** Most relationship extraction works from S2 citation contexts + abstracts.

PDFs are needed only for:
1. **Foundational papers (~50-100)** where S2 citation context is missing or too shallow — get via university library institutional access
2. **Quality audit** — spot-check LLM relationship labels against full paper text

Marketing journal PDFs (Marketing Science, JMR, etc.) are behind paywalls (INFORMS, AMA publishers). Legal access routes:
- University library proxy / institutional subscription (most business schools have these)
- S2 `openAccessPdf` field — some papers have open access versions
- SSRN / NBER working paper versions — many marketing papers circulate as free preprints
- Author personal websites — professors often host their own PDFs

---

## Architecture

### Design Principles

1. **Data file is the product** — the graph is a static, distributable artifact (SQLite primary, JSON for subgraph export), not a running service
2. **Zero-dependency access** — any agent that can read a file or run a CLI command can use it (SQLite drivers exist in every language)
3. **Construction is offline** — expensive LLM processing happens once at build time, not at query time
4. **Protocol-agnostic** — not tied to MCP or any specific agent framework
5. **Versioned artifacts** — each graph release is tagged (e.g., `quant-marketing-2026Q1`) so agents and users know what data they have
6. **Offline-first** — all query-time operations work without internet; network is only needed for `init` (first download) and `update`

### Why SQLite, Not Neo4j

Informed by our architecture research:

| Factor | Neo4j | SQLite |
|--------|-------|--------|
| Deployment | Server process, JVM, config | Single file, zero config |
| Distribution | Users must install Neo4j | File ships with pip package |
| Query language | Cypher (specialized) | SQL (universal) + FTS5 |
| Our scale (3k nodes, 37k edges) | Massive overkill | Perfect fit |
| Precedent | Graphiti, Cognee, NLP-AKG use it | Airbnb KG uses relational DB; GraphRAG uses Parquet files |
| Offline-first | Requires running server | File-based, always offline |
| Multi-hop traversal | Native graph traversal | Recursive CTEs (adequate for depth 3-4) |

Airbnb's KG architecture validates this: they use a relational database (one table for nodes, one for edges) rather than a graph DB, citing operational simplicity. At our scale (~3k papers), SQLite with FTS5 full-text search gives us everything we need.

### System Overview

```
CONSTRUCTION (offline, one-time)              ACCESS (runtime, zero-cost)
┌─────────────────────────────┐              ┌──────────────────────────┐
│ Semantic Scholar API        │              │ Option A: File Read      │
│   ↓                         │              │   agent reads .json      │
│ Paper metadata + citations  │              │                          │
│   ↓                         │              │ Option B: CLI            │
│ Citation contexts + intents │   ┌──────┐   │   paperkg query "BLP"    │
│   ↓                         │──→│ Graph │──→│   paperkg lineage <id>   │
│ LLM: fine-grained relation  │   │.sqlite│   │   paperkg frontier <topic│
│   classification            │   └──────┘   │                          │
│   ↓                         │              │ Option C: Python import  │
│ Expert review + correction  │              │   from paperkg import g  │
│   ↓                         │              │                          │
│ Graph assembly + validation │              │ Option D: MCP (optional) │
└─────────────────────────────┘              └──────────────────────────┘
```

### Data Directory

```
~/.paperkg/
  quant-marketing/
    graph.sqlite          # main graph database
    meta.json             # version, build date, corpus stats
    overlay.sqlite        # user-local annotations/corrections (merged at query time)
```

### Graph Data Model

Informed by the architecture analysis — we use a **property graph in SQLite** (like Airbnb's approach), with **natural language `fact` fields** (like Graphiti's pattern), and **token-budgeted serialization** (like GraphRAG's approach).

```
Node (Paper):
  - id: S2 paperId (TEXT PK)
  - doi: DOI string (for cross-referencing)
  - title, year, venue, authors (TEXT)
  - abstract, tldr (TEXT)
  - citation_count, influential_citation_count (INT)
  - topics: extracted research topics (TEXT, comma-separated)
  - methods: methodology used (TEXT)
  - node_type: "core" | "boundary" (TEXT)
  #   core = papers in our domain journals
  #   boundary = papers outside domain but cited by core papers
  #   Core→boundary edges ARE fully classified
  #   Boundary→boundary edges are OMITTED

Embedding (separate table, loaded on demand):
  - paper_id → SPECTER vector (BLOB, 768-dim float)

Edge (Relationship):
  - source_id → target_id (citing → cited)
  - s2_intents: TEXT (JSON array: Background, Method, ResultExtension)
  - s2_contexts: TEXT (JSON array of citing sentences)
  - s2_is_influential: BOOL
  - fine_type: TEXT ("extends_model", etc.)  # from LLM
  - fact: TEXT  # natural language assertion (Graphiti pattern)
  #   e.g., "Nevo (2001) provides a practitioner's guide to implementing
  #          BLP's random coefficients logit demand estimation model"
  - confidence: REAL (0.0-1.0)
  - context_source: TEXT ("s2_context" | "abstract_only" | "pdf_deep_read")
  - expert_verified: BOOL

FTS5 Index:
  - Full-text search on: titles, abstracts, fact descriptions, topics, methods
```

**Why the `fact` field matters:** This is the key design decision informed by our research. Graphiti stores a natural language assertion on every edge (e.g., "Alice works at TechCorp since 2023"). When an agent retrieves edges, the `fact` field is immediately comprehensible without needing to interpret structured fields. The `fine_type` field enables programmatic filtering, but the `fact` field is what the agent actually reads.

### Context Window Serialization (Token Budgeting)

Learned from GraphRAG (the only project that does this right):

```python
def serialize_subgraph(papers, edges, max_tokens=4000, tokenizer=None):
    """
    Serialize a subgraph for agent context injection.
    Papers sorted by relevance score, edges included inline.
    Truncates when token budget is exceeded.
    """
    output_lines = []
    token_count = 0

    for paper in sorted(papers, key=lambda p: p.relevance, reverse=True):
        paper_block = format_paper(paper, edges)  # title, year, relationships
        block_tokens = count_tokens(paper_block, tokenizer)
        if token_count + block_tokens > max_tokens:
            break
        output_lines.append(paper_block)
        token_count += block_tokens

    return "\n".join(output_lines)
```

Output format — compact, LLM-friendly:
```
## BLP (1995) - Berry, Levinsohn, Pakes
"Automobile Prices in Market Equilibrium" | Econometrica
→ Extended by: Nevo (2001) "Practitioner's guide to BLP estimation"
→ Extended by: Petrin (2002) "Adds micro-level data to BLP instruments"
→ Applied to healthcare by: Ho (2006) "Insurer-hospital bargaining"
→ Improved estimation by: Dubé et al. (2012) "MPEC approach to BLP"
← Builds on: Berry (1994) "Inversion theorem for market shares"
```

### Relationship Taxonomy Discovery

**Do NOT predefine a fixed taxonomy.** Instead:

1. **Extract**: For each citation pair, feed the S2 citing sentence(s) + both abstracts to LLM. Ask for:
   - A free-form `fact` description (1 sentence — this becomes the edge's `fact` field)
   - A suggested relationship category
   - Confidence score

2. **Cluster**: After processing a batch (~500 pairs), embed all descriptions and cluster. See what natural categories emerge.

3. **Expert validate**: Domain expert reviews clusters, names them, merges/splits.

4. **Re-label** (not re-classify): Map existing free-form descriptions to the finalized taxonomy using embedding similarity or lightweight matching. Keep the `fact` descriptions as ground truth; the taxonomy label is a derived field. This avoids re-running LLM on all pairs when the taxonomy evolves.

**Reference: NLP-AKG's 29 relation types** showed that academic KGs benefit from rich inter-paper relations. But their 2 inter-paper types (`direct_use`, `task_related`) are too coarse. Our taxonomy should emerge from the data and capture marketing-specific patterns.

Expected categories (hypothesis, to be validated by data):
- Methodological: extends_model, improves_estimation, proposes_new_method, applies_method_to_new_domain
- Intellectual: builds_on_theory, contradicts_finding, reconciles, generalizes
- Empirical: uses_same_data, replicates, new_empirical_context
- Structural: is_survey_of, is_foundational_for, is_comment_on

But the actual taxonomy should emerge from the data, not from this list.

### LLM Prompt Design (sketch for Phase 0 testing)

```
Input:
  Citing paper: {title} ({year}) - {abstract_excerpt}
  Cited paper: {title} ({year}) - {abstract_excerpt}
  Citation context (if available): "{context_sentence}"
  S2 intent: {intent}

Output (JSON):
  {
    "fact": "One sentence describing the relationship in plain English",
    "suggested_category": "free-form category label",
    "direction": "builds_on | responds_to | applies | compares",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation (for debugging, not stored in graph)"
  }
```

When multiple citation contexts exist for the same pair, concatenate them and ask the LLM to synthesize the overall relationship.

### Error Handling

- Missing graph: `paperkg` commands print "No graph found. Run: paperkg init quant-marketing" and exit with code 1
- Zero results: print "No papers matched '<query>'. Try broader terms." with suggestions based on FTS5 spellfix
- Ambiguous paper reference: print top-5 matches and ask user to be more specific
- Outdated graph: `paperkg stats` shows graph version and age; suggests `paperkg update` if > 6 months old

---

## Scope: Quantitative Marketing

### Why This Domain First

- **Small enough to complete**: ~2,500 papers means one person can build and curate the full graph
- **Domain expertise available**: the builder has deep knowledge to make curation and verification judgments
- **Methodologically dense**: the field is built on model extensions, estimation improvements, and method applications -- exactly the relationship types where fine-grained classification adds the most value over simple citation links
- **Underserved by existing tools**: CS-centric tools (S2, Connected Papers) have poor coverage of social science journals; marketing researchers are not well served by current offerings
- **Clear community**: identifiable set of researchers, conferences, and journals makes distribution and feedback collection straightforward

### Seed Journals / Venues
- Marketing Science
- Journal of Marketing Research (JMR)
- Management Science (marketing papers)
- Quantitative Marketing and Economics (QME)
- Journal of Marketing (JM) — select quantitative papers
- RAND Journal of Economics — select papers with marketing relevance

### Corpus Construction Strategy

1. **Seed papers**: Top-cited papers in quant marketing (BLP 1995, Rust/Zeithaml/Lemon 2004, Rossi/Allenby 2003, etc.)
2. **Expand via citations**: For each seed, get all citations and references from S2
3. **Filter by venue**: Keep only papers from seed journals
4. **Expand iteratively**: 2-3 rounds of citation expansion
5. **Expert curation**: Review the boundary — which papers are in/out

Expected corpus size: **1,500 - 3,000 papers** (manageable, valuable).

### Cost Estimation

```
Corpus: ~2,500 papers
In-corpus citation pairs: ~2,500 × 10-15 avg in-corpus citations = ~25,000-37,500 pairs
  (Note: 15 is optimistic for marketing; 10 may be more realistic. Validate in Phase 0.)

S2 provides: citing sentences + 3-class intent for SOME pairs (FREE)
  WARNING: S2 context coverage for non-CS, non-open-access journals may be 30-50%, not 90%.
  Pairs without S2 contexts use abstract-only fallback (higher token cost, lower quality).

LLM fine-grained classification:
  Scenario A (S2 contexts available, ~50% of pairs):
    Input per pair: ~300 tokens (citing sentence + abstract excerpts)
  Scenario B (abstract-only fallback, ~50% of pairs):
    Input per pair: ~600 tokens (both full abstracts)
  Output per pair: ~100 tokens (fact + category + confidence)
  Weighted average: ~30,000 pairs × 550 tokens = ~16.5M tokens
  Cost: ~$4 (Haiku) or ~$50 (Sonnet)
  Realistic cost with re-runs and prompt iteration: 2-3x base → ~$12-150

PDF deep-read for top papers: ~100 papers × ~5,000 tokens = 0.5M tokens
  Cost: ~$0.50 (Haiku)

S2 API calls:
  Paper details: ~2,500 calls (batch: 5 calls × 500 papers)
  Citations per paper: ~2,500 calls
  Total: ~5,000 API calls at 1/sec = ~1.5 hours
  Cost: FREE

Total realistic cost: ~$15-150 depending on model choice and iteration count
```

### Fallback Strategy: When S2 Citation Contexts Are Missing

For citation pairs without S2 `contexts`:
1. Use both paper abstracts + S2 `intents` (if available) as input to LLM
2. Mark these edges with `context_source: "abstract_only"` (lower confidence expected)
3. Prioritize PDF deep-read for high-citation foundational papers lacking contexts
4. Accept that abstract-only edges will have lower relationship granularity

---

## Access Layer: CLI + File

### CLI Commands

```bash
# Install
pip install paperkg

# First run (downloads graph data to ~/.paperkg/)
paperkg init quant-marketing

# Lookup papers by fuzzy author-year or title (returns paper IDs)
paperkg lookup "BLP 1995"                      # fuzzy match by author-year
paperkg lookup "demand estimation cereal"      # fuzzy match by title fragment

# Core commands (accept paper ID, author-year shorthand, or title fragment)
paperkg query "BLP demand estimation"          # search papers
paperkg lineage "BLP 1995"                     # trace intellectual lineage
paperkg frontier "structural models"           # current research frontier
paperkg compare "BLP 1995" "Nevo 2001"         # relationship between two papers
paperkg methodology "random coefficients"      # papers using this method
paperkg subgraph "dynamic pricing" --depth 2   # extract subgraph around a topic
paperkg related-work "Bayesian demand estimation" # structured related work outline
paperkg stats                                  # corpus overview
paperkg update                                 # check for and download graph updates

# Agent-friendly: output as structured JSON
paperkg query "BLP" --format json
paperkg lineage "BLP 1995" --format json --depth 3

# Export for context loading (with token budget control)
paperkg context "demand estimation" > context.md                    # markdown for CLAUDE.md
paperkg context "demand estimation" --max-tokens 4000 > context.md  # fit within agent context budget
paperkg context "demand estimation" --max-papers 20 > context.md    # limit number of papers
```

### Agent Integration Patterns

**Pattern 1: CLI tool use (any agent)**
```
Agent calls: paperkg query "instrumental variables in demand estimation" --format json
Agent receives: structured list of papers with relationships (token-budgeted)
Agent uses this context to answer user's question
```

**Pattern 2: Context file (Claude Code / Cursor)**
```
# In CLAUDE.md or .cursorrules:
# For research context, run: paperkg context "<topic>" and read the output
```

**Pattern 3: Python library (programmatic)**
```python
from paperkg import PaperKG
kg = PaperKG("quant-marketing")
lineage = kg.lineage("BLP 1995", depth=3)
frontier = kg.frontier("structural models", since=2023)
```

**Pattern 4: MCP server (optional add-on)**
```
If MCP is needed, it's a thin wrapper over the CLI. But not the primary interface.
```

### Example Research Workflows

**Workflow 1: New PhD student mapping a subfield**
```
Student: "I'm starting research on dynamic pricing. What should I read?"
Agent runs: paperkg subgraph "dynamic pricing" --depth 2 --format json
Agent receives: 30 papers organized by relationship (foundational → extensions → applications)
Agent synthesizes: "The field starts with Gallego & van Ryzin (1994)..."
```

**Workflow 2: Positioning a new paper against existing literature**
```
Researcher: "I'm writing a paper on Bayesian estimation of demand models."
Agent runs: paperkg related-work "Bayesian demand estimation" --max-papers 25
Agent drafts: a related work outline with proper positioning
```

**Workflow 3: Finding methodological gaps**
```
Researcher: "Has anyone applied synthetic control to marketing problems?"
Agent runs: paperkg methodology "synthetic control" --format json
Agent receives: either matching papers or empty result indicating opportunity
```

### Output Format: Provenance by Default

All CLI output includes provenance so users can verify LLM-generated labels:
```
Edge: Nevo (2001) → BLP (1995)
  Relationship: extends_model (confidence: 0.94)
  Fact: "Provides a practitioner's guide to implementing BLP's random coefficients logit model"
  Evidence: "This paper is a practical guide to the method developed in Berry, Levinsohn and Pakes (1995)..."
  Source: S2 citation context | Expert verified: No
```

---

## Phases

### Phase 0: Feasibility Validation
- Pull BLP (1995) citation network (~100 papers) using S2 Graph API
- **Measure S2 citation context coverage rate**: what % of citation pairs in Marketing Science / JMR have `contexts`? If < 40%, the fallback strategy becomes the primary path
- Examine S2 citation contexts quality for marketing papers
- Test LLM relationship extraction on ~200 citation pairs (both with and without citation contexts)
- Design and test the LLM prompt (structured output, fact generation quality)
- **Human baseline**: classify 50-100 pairs independently; measure inter-annotator agreement (Cohen's kappa)
- Cluster → validate taxonomy emergence
- Test venue name normalization (how noisy is S2's `venue` field for marketing journals?)
- **Go/No-Go decision based on**: (1) S2 context coverage rate, (2) LLM relationship quality, (3) human agreement baseline

### Phase 1: Corpus Construction
- Define seed papers with expert input
- Build S2 data pipeline (metadata + citations + contexts)
- Venue name normalization (build mapping of S2 venue strings → canonical journal names)
- Deduplication: detect and merge working paper / published version pairs
- Iterative corpus expansion with venue filtering
- Expert review of corpus boundary
- Validate corpus against reference list (PhD syllabi + survey papers)

### Phase 2: Relationship Extraction
- Batch LLM processing of all citation pairs
- Taxonomy discovery via clustering
- Expert validation of taxonomy
- Re-labeling with finalized taxonomy
- Quality audit (random sample expert verification)

### Phase 3: Graph Assembly + CLI
- SQLite schema implementation with FTS5 full-text index
- Token-budgeted context serialization (GraphRAG pattern)
- CLI tool with core commands
- Python package with programmatic access
- Graph validation: cycle detection, orphan node check, duplicate edge check
- Testing with real research questions

### Phase 4: Distribution + Launch
- Package as pip installable (Python-only)
- GitHub README (GitNexus-style, clear value prop)
- Example use cases with real research questions
- Blog post with visual: "The BLP Family Tree"
- **Targeted seeding**: identify 3-5 quant marketing professors; send personalized demo of their own paper's lineage
- Broader outreach: marketing PhD student communities, INFORMS marketing science conference

### Phase 5: Iteration + Generalization
- Incorporate user feedback
- Improve relationship quality based on expert corrections
- Optional: MCP server add-on
- Optional: web visualization of the graph
- Academic paper: write up methodology contribution
- **Name decision**: finalize project name before public launch

### Generalization to Other Domains

The construction pipeline is designed to be reusable:
1. A domain expert defines seed papers, seed journals, and corpus boundary rules
2. The S2 data pipeline runs identically (venue normalization map is domain-specific)
3. LLM relationship extraction uses the same prompt structure; taxonomy discovered per-domain
4. The CLI and access layer work unchanged (just a different `--domain` flag)

Each domain graph is an independent SQLite file. Users install only the domains they need.

Near-term expansion candidates (require a domain expert collaborator):
- **Empirical IO / Industrial Organization**: heavily overlaps with quant marketing
- **Causal Inference in Economics**: well-defined methodological lineage
- **Computational Linguistics / NLP**: already well-covered by S2

---

## Success Criteria

1. **A quant marketing PhD student can ask an agent "trace the evolution of BLP demand estimation" and get a structured, accurate answer in one tool call**
2. **Relationship type accuracy on expert-reviewed sample:**
   - Taxonomy label accuracy > 85% for edges with S2 citation contexts
   - Taxonomy label accuracy > 70% for abstract-only edges
   - `fact` description judged "useful" by expert > 90%
   - Critical errors (e.g., "extends" classified as "contradicts") < 2%
   - For top-100 most-cited papers: 100% expert-verified edges
3. **Setup takes < 2 minutes (install + first query)**
4. **Corpus covers > 90% of papers from a reference list** (derived from quant marketing PhD syllabi + survey papers)

---

## Open Questions

1. Should the graph data be shipped with the package (embedded) or downloaded separately?
   - Embedded: simpler UX, but package size grows
   - Separate: smaller package, but adds a download step
   - Recommendation: embedded for MVP, separate download for large corpora

2. How to handle papers at domain boundaries?
   - Include them as "boundary" nodes with basic metadata
   - Core→boundary edges are fully classified; boundary→boundary edges omitted

3. Update cadence?
   - Quarterly batch updates; community can submit PRs to add papers

4. Should users be able to add their own annotations/corrections?
   - Yes, via a local overlay file that merges with the distributed graph

5. Name?
   - "PaperKG" is too generic and uses jargon
   - Consider names evoking intellectual lineage: Lineage, ScholarTree, PaperDNA
   - **Decision required before Phase 4 launch**

6. S2 API dependency risk
   - Mitigation: abstract the data source behind an interface so OpenAlex or CrossRef could substitute
   - For MVP: acceptable risk; S2 is free and stable
