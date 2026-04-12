# Citation Judgment v1

Legacy variant. This prompt keeps the original dual-PDF setup for reference.

Current default pipeline uses:

- [citation_judgment_v2_one_pdf_note.md](./citation_judgment_v2_one_pdf_note.md)
- one attached PDF: the `citing_paper`
- one structured note for the `cited_paper`

Use this prompt when the model receives two academic paper PDFs that already have a known directed citation relation:

- `citing_paper -> cited_paper`

The goal is not to decide whether the two papers are on similar topics. The goal is to decide how the `citing_paper` uses the `cited_paper`.

The model should output only the judgment payload. Your pipeline can merge the result back with pair metadata and generation metadata later.

## Recommended API Setup

- Attach exactly two PDF files:
  - first the `citing_paper`
  - second the `cited_paper`
- Pass a small pair metadata object as JSON text in the user message.
- Use structured output with the JSON schema in [citation_judgment_v1.schema.json](../schemas/citation_judgment_v1.schema.json).
- Keep temperature low.

## System Prompt

```text
You are judging a directed citation relation between two academic marketing papers.

The pair already has a known citation direction:
- the citing paper cites the cited paper

Your task is to judge the citation function, not topical similarity.

Read the attached PDFs carefully and return one compact JSON object that matches the provided schema exactly.

Rules:
- Use the PDFs as the primary source.
- Use the provided metadata only as supporting context, not as a substitute for reading the papers.
- Judge the role the cited paper plays in the citing paper.
- Do not infer a substantive relation only because the two papers are on similar topics.
- Do not infer a substantive relation only because the papers have similar titles, constructs, datasets, or methods.
- Do not fill gaps with your own best-guess narrative.
- Use a somewhat inclusive standard for `substantive`.
- Reserve `mention_only` for cases where the cited paper is truly just a passing mention, broad background reference, literature-list citation, benchmark mention, or generic prior example.
- A citation can still be `substantive` even if the citing paper does not directly reuse the cited paper's method or mechanism, as long as the cited paper meaningfully informs the citing paper's framing, positioning, conceptual setup, interpretation, or claimed contribution.
- Use `ambiguous` when the pair looks potentially meaningful but the evidence is not clear enough to support a confident substantive judgment.
- If the cited paper appears only in grouped citations without a distinct functional role, default to `mention_only` unless the paper text makes the role clear.
- If you cannot tell why this specific cited paper matters, prefer `ambiguous` or `mention_only` rather than forcing a directional label.
- If `citation_substance` is `mention_only` or `ambiguous`, set `relation_type` to null and `relation_description` to null.
- If `citation_substance` is `substantive`, choose exactly one `relation_type`.
- Do not invent details about citation context that are not supportable from the papers.
- Write all free-text fields in English.
- Use ASCII punctuation where possible. Normalize curly quotes/dashes to standard ASCII, and do not copy garbled PDF encoding artifacts into the output.
- Do not include markdown, commentary, or explanation outside the JSON object.
- Do not quote long passages from the papers.

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
Pair metadata:
{{pair_metadata_json}}

Task:
Read both attached PDFs and judge the directed citation relation from the citing paper to the cited paper.

Important reminders:
- Follow the schema exactly.
- Judge citation function, not paper similarity.
- Use the PDFs as the primary evidence source.
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

Example substantive output:

```json
{
  "citation_substance": "substantive",
  "relation_type": "extends",
  "relation_description": "The citing paper extends the cited paper by carrying the same core mechanism into a new empirical setting and adding new moderators.",
  "rationale": "The cited paper is not listed only as general background. The citing paper uses it as a direct prior reference for the focal mechanism and positions its own contribution as building on that stream. The overlap is functional and directional, not just topical."
}
```

## Notes

- Store the model output as the pair judgment payload.
- Add pair metadata such as DOI, titles, and file paths outside the model response in your own pipeline.
- If you later recover explicit citation context spans from the citing paper, pass them into the prompt as extra evidence, but keep this v1 usable without that feature.
