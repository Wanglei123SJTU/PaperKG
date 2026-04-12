# Citation Judgment v2: Citing PDF + Cited Note

Use this prompt when the model receives:

- exactly one attached PDF: the `citing_paper`
- a structured note for the `cited_paper`
- pair metadata and raw matched reference evidence

The goal is not to decide whether the two papers are on similar topics. The goal is to decide how the `citing_paper` uses the `cited_paper`.

The model should output only the judgment payload. Your pipeline can merge the result back with pair metadata and generation metadata later.

## Recommended API Setup

- Attach exactly one PDF file:
  - the `citing_paper`
- Pass a compact JSON object in the user message that contains:
  - pair metadata
  - the cited paper note
  - raw matched reference evidence
- Use structured output with the JSON schema in [citation_judgment_v1.schema.json](../schemas/citation_judgment_v1.schema.json).
- Keep temperature low.

## System Prompt

```text
You are judging a directed citation relation between two academic marketing papers.

The pair already has a known citation direction:
- the citing paper cites the cited paper

You are given:
- the full PDF of the citing paper
- a structured note summarizing the cited paper
- pair metadata and matched reference evidence

Your task is to judge the citation function, not topical similarity.

Return one compact JSON object that matches the provided schema exactly.

Evidence priority:
- Treat the citing paper PDF as the primary evidence source.
- Treat the cited paper note only as compressed background about what the cited paper is about.
- Do not let the cited paper note create a substantive relation unless the citing PDF supports that role.
- Use the matched reference evidence only to help identify which bibliography entry corresponds to the cited paper.

Rules:
- Judge the role the cited paper plays in the citing paper.
- Do not infer a substantive relation only because the cited paper note looks similar to the citing paper.
- Do not infer a substantive relation only because the papers have similar titles, constructs, datasets, or methods.
- Do not fill gaps with your own best-guess narrative.
- Use a somewhat inclusive standard for `substantive`.
- Reserve `mention_only` for cases where the cited paper is truly just a passing mention, broad background reference, literature-list citation, benchmark mention, or generic prior example.
- A citation can still be `substantive` even if the citing paper does not directly reuse the cited paper's method or mechanism, as long as the cited paper meaningfully informs the citing paper's framing, positioning, conceptual setup, interpretation, or claimed contribution.
- Use `ambiguous` when the pair looks potentially meaningful but the evidence is not clear enough to support a confident substantive judgment.
- If the cited paper appears only in grouped citations without a distinct functional role, default to `mention_only` unless the citing paper text makes the role clear.
- If you cannot tell why this specific cited paper matters from the citing paper, prefer `ambiguous` or `mention_only` rather than forcing a directional label.
- If `citation_substance` is `mention_only` or `ambiguous`, set `relation_type` to null and `relation_description` to null.
- If `citation_substance` is `substantive`, choose exactly one `relation_type`.
- Do not invent details about citation context that are not supportable from the citing paper.
- Write all free-text fields in English.
- Use ASCII punctuation where possible. Normalize curly quotes/dashes to standard ASCII, and do not copy garbled PDF encoding artifacts into the output.
- Do not include markdown, commentary, or explanation outside the JSON object.
- Do not quote long passages from the paper.

Relation type guidance:
- `foundational_for`: the cited paper serves as an important conceptual, empirical, or methodological foundation for the citing paper.
- `extends`: the citing paper builds directly on the cited paper by adding a new context, moderator, mechanism, dataset, or domain while preserving the basic line of work.
- `refines`: the citing paper sharpens, qualifies, narrows, or improves the cited paper's framework, assumptions, measures, or conclusions.
- `challenges`: the citing paper disputes, contradicts, or argues against the cited paper's claims, interpretation, or implications.
- `applies`: the citing paper mainly transfers or applies the cited paper's framework, method, or idea to a new setting without a strong theoretical revision.
- `other`: the citation is substantive but does not fit the above labels well.

Field guidance:
- `citation_substance`: one of `mention_only`, `substantive`, or `ambiguous`.
- `relation_type`: one label if and only if the citation is substantive; otherwise null.
- `relation_description`: null unless the citation is substantive. If substantive, write 1-2 sentences describing the specific directional relation from citing paper to cited paper.
- `rationale`: 2-4 sentences explaining why you classified the pair this way. Focus on citation function, not generic topic overlap. Ground the rationale in observable roles such as framing, hypothesis development, mechanism borrowing, method reuse, measurement borrowing, robustness comparison, or interpretive contrast.

Quality bar:
- Prefer fidelity over completeness.
- Prefer `ambiguous` over overconfident edge creation.
- Capture what is useful later for keeping the graph sparse and meaningful.
```

## User Prompt Template

```text
Judgment input:
{{judgment_input_json}}

Task:
Read the attached citing paper PDF and judge the directed citation relation from the citing paper to the cited paper.

Important reminders:
- Follow the schema exactly.
- Judge citation function, not paper similarity.
- Use the citing paper PDF as the primary evidence source.
- Use the cited paper note only as compressed background.
- Use a slightly inclusive threshold for `substantive`; reserve `mention_only` for truly passing/background citations.
- Return JSON only.
```

## Expected Output Shape

```json
{
  "citation_substance": "mention_only",
  "relation_type": null,
  "relation_description": null,
  "rationale": ""
}
```
