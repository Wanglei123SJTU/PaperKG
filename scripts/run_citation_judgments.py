import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai_pdf_runner_utils import (
    ensure_uploaded_pdf,
    extract_structured_payload,
    invoke_structured_pdf_task,
    invoke_structured_pdf_task_http,
    load_cache,
    load_csv_rows,
    load_json,
    load_prompt_sections,
    make_client,
    now_run_name,
    repo_root,
    resolve_api_keys,
    response_to_json_dict,
    sanitize_filename,
    save_cache,
    usage_summary,
    write_csv_rows,
)


def resolve_maybe_absolute(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/jmr_2000_2025/citation_judgments/manifest.csv")
    parser.add_argument("--prompt", default="prompts/citation_judgment_v2_one_pdf_note.md")
    parser.add_argument("--schema", default="schemas/citation_judgment_v1.schema.json")
    parser.add_argument("--out-root", default="data/jmr_2000_2025/citation_judgments/runs")
    parser.add_argument("--file-cache", default="data/jmr_2000_2025/openai_file_cache.json")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=1000)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--run-name", default="")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--api-backend",
        choices=["openai_client", "responses_http_inline_file"],
        default="responses_http_inline_file",
    )
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--api-key", action="append", default=[])
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--request-connect-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--request-max-attempts", type=int, default=4)
    parser.add_argument("--request-initial-backoff-seconds", type=float, default=2.0)
    args = parser.parse_args()

    if args.api_backend == "responses_http_inline_file" and not args.api_base_url:
        raise SystemExit("--api-base-url is required when --api-backend=responses_http_inline_file")
    if args.api_backend == "openai_client" and args.max_concurrency > 1:
        raise SystemExit("Concurrent execution is only supported for --api-backend=responses_http_inline_file")

    root = repo_root()
    manifest_path = root / args.manifest
    prompt_path = root / args.prompt
    schema_path = root / args.schema
    out_root = root / args.out_root
    cache_path = root / args.file_cache

    run_name = args.run_name or now_run_name()
    run_dir = out_root / run_name
    judgments_dir = run_dir / "judgments"
    responses_dir = run_dir / "responses"
    errors_dir = run_dir / "errors"
    run_dir.mkdir(parents=True, exist_ok=True)
    judgments_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)
    errors_dir.mkdir(parents=True, exist_ok=True)

    system_prompt, user_template = load_prompt_sections(prompt_path)
    schema = load_json(schema_path)
    schema_name = schema.get("title", "citation_judgment_v1").replace(" ", "_").lower()
    manifest_rows = load_csv_rows(manifest_path)

    if args.offset:
        manifest_rows = manifest_rows[args.offset:]
    if args.limit > 0:
        manifest_rows = manifest_rows[: args.limit]

    (run_dir / "prompt_snapshot.md").write_text(prompt_path.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "schema_snapshot.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "manifest_snapshot.csv").write_text(manifest_path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
    (run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "prompt": str(prompt_path),
                "schema": str(schema_path),
                "model": args.model,
                "reasoning_effort": args.reasoning_effort,
                "temperature": args.temperature,
                "max_output_tokens": args.max_output_tokens,
                "offset": args.offset,
                "limit": args.limit,
                "sleep_seconds": args.sleep_seconds,
                "api_backend": args.api_backend,
                "api_base_url": args.api_base_url,
                "max_concurrency": args.max_concurrency,
                "request_connect_timeout_seconds": args.request_connect_timeout_seconds,
                "request_timeout_seconds": args.request_timeout_seconds,
                "request_max_attempts": args.request_max_attempts,
                "request_initial_backoff_seconds": args.request_initial_backoff_seconds,
                "api_key_slots": len(args.api_key) if args.api_key else 0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    api_keys = resolve_api_keys(args.api_key or None)
    client = None
    cache: dict[str, dict[str, object]] = {}
    if args.api_backend == "openai_client":
        client = make_client(api_key=api_keys[0], base_url=args.api_base_url or None)
        cache = load_cache(cache_path)

    summary_rows: list[dict[str, object]] = []
    summary_fields = [
        "pair_id",
        "status",
        "response_id",
        "model",
        "requested_reasoning_effort",
        "returned_reasoning_effort",
        "api_key_slot",
        "citation_substance",
        "relation_type",
        "output_path",
        "raw_response_path",
        "error_path",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "error",
    ]

    def process_row(row_index: int, row: dict[str, str]) -> dict[str, object]:
        pair_id = row.get("pair_id") or sanitize_filename(
            f"{row.get('citing_resolved_doi', '')}__cites__{row.get('cited_resolved_doi', '')}"
        )
        judgment_path = judgments_dir / f"{pair_id}.json"
        response_path = responses_dir / f"{pair_id}.json"
        error_path = errors_dir / f"{pair_id}.txt"

        if args.skip_existing and judgment_path.exists():
            existing = load_json(judgment_path)
            return {
                "pair_id": pair_id,
                "status": "skipped_existing",
                "response_id": "",
                "model": args.model,
                "requested_reasoning_effort": args.reasoning_effort,
                "returned_reasoning_effort": "",
                "api_key_slot": "",
                "citation_substance": existing.get("citation_substance", ""),
                "relation_type": existing.get("relation_type", ""),
                "output_path": str(judgment_path),
                "raw_response_path": str(response_path) if response_path.exists() else "",
                "error_path": str(error_path) if error_path.exists() else "",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "error": "",
            }

        try:
            citing_pdf_path = resolve_maybe_absolute(root, row["citing_pdf_path"])
            cited_note = load_json(resolve_maybe_absolute(root, row["cited_note_path"]))
            reference_evidence = json.loads(row["matched_reference_evidence_json"])
            pair_metadata = {
                "pair_id": pair_id,
                "citing_official_year": row["citing_official_year"],
                "citing_query_doi": row["citing_query_doi"],
                "citing_resolved_doi": row["citing_resolved_doi"],
                "citing_title": row["citing_title"],
                "cited_official_year": row["cited_official_year"],
                "cited_query_doi": row["cited_query_doi"],
                "cited_resolved_doi": row["cited_resolved_doi"],
                "cited_title": row["cited_title"],
                "matched_reference_count": int(row.get("matched_reference_count") or 0),
                "match_type_breakdown": json.loads(row["match_type_breakdown"]) if row.get("match_type_breakdown") else {},
            }
            user_prompt = user_template.replace(
                "{{judgment_input_json}}",
                json.dumps(
                    {
                        "pair_metadata": pair_metadata,
                        "cited_paper_note": cited_note,
                        "raw_matched_reference_evidence": reference_evidence,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            if args.api_backend == "openai_client":
                assert client is not None
                file_id = ensure_uploaded_pdf(client, citing_pdf_path, cache, cache_path)
                response = invoke_structured_pdf_task(
                    client,
                    model=args.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    file_ids=[file_id],
                    schema_name=schema_name,
                    schema=schema,
                    temperature=args.temperature,
                    max_output_tokens=args.max_output_tokens,
                    reasoning_effort=args.reasoning_effort,
                )
                api_key_slot = 0
            else:
                api_key_slot = row_index % len(api_keys)
                response = invoke_structured_pdf_task_http(
                    api_key=api_keys[api_key_slot],
                    base_url=args.api_base_url,
                    model=args.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    pdf_paths=[citing_pdf_path],
                    schema_name=schema_name,
                    schema=schema,
                    temperature=args.temperature,
                    max_output_tokens=args.max_output_tokens,
                    reasoning_effort=args.reasoning_effort,
                    connect_timeout_seconds=args.request_connect_timeout_seconds,
                    timeout_seconds=args.request_timeout_seconds,
                    max_attempts=args.request_max_attempts,
                    initial_backoff_seconds=args.request_initial_backoff_seconds,
                )

            payload = extract_structured_payload(response, schema)
            judgment_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            response_dict = response_to_json_dict(response)
            response_path.write_text(json.dumps(response_dict, ensure_ascii=False, indent=2), encoding="utf-8")
            usage = usage_summary(response)
            returned_reasoning_effort = str((response_dict.get("reasoning") or {}).get("effort") or "")

            return {
                "pair_id": pair_id,
                "status": "ok",
                "response_id": str(response_dict.get("id", "")),
                "model": args.model,
                "requested_reasoning_effort": args.reasoning_effort,
                "returned_reasoning_effort": returned_reasoning_effort,
                "api_key_slot": api_key_slot,
                "citation_substance": payload.get("citation_substance", ""),
                "relation_type": payload.get("relation_type", ""),
                "output_path": str(judgment_path),
                "raw_response_path": str(response_path),
                "error_path": "",
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "total_tokens": usage["total_tokens"],
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            error_path.write_text(repr(exc), encoding="utf-8")
            return {
                "pair_id": pair_id,
                "status": "error",
                "response_id": "",
                "model": args.model,
                "requested_reasoning_effort": args.reasoning_effort,
                "returned_reasoning_effort": "",
                "api_key_slot": "",
                "citation_substance": "",
                "relation_type": "",
                "output_path": "",
                "raw_response_path": "",
                "error_path": str(error_path),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "error": repr(exc),
            }

    total = len(manifest_rows)
    if args.api_backend == "responses_http_inline_file" and args.max_concurrency > 1:
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            futures = {
                executor.submit(process_row, index, row): index
                for index, row in enumerate(manifest_rows, start=0)
            }
            completed = 0
            for future in as_completed(futures):
                completed += 1
                result = future.result()
                summary_rows.append(result)
                write_csv_rows(run_dir / "summary.csv", summary_fields, summary_rows)
                print(f"{completed}/{total} {result['pair_id']}")
    else:
        for index, row in enumerate(manifest_rows, start=0):
            result = process_row(index, row)
            summary_rows.append(result)
            write_csv_rows(run_dir / "summary.csv", summary_fields, summary_rows)
            print(f"{index + 1}/{total} {result['pair_id']}")
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    if args.api_backend == "openai_client":
        save_cache(cache_path, cache)

    citation_substance_counts: dict[str, int] = {}
    relation_type_counts: dict[str, int] = {}
    returned_reasoning_counts: dict[str, int] = {}
    for row in summary_rows:
        if row["status"] != "ok":
            continue
        substance = str(row["citation_substance"] or "")
        relation_type = str(row["relation_type"] or "")
        returned_reasoning = str(row["returned_reasoning_effort"] or "")
        citation_substance_counts[substance] = citation_substance_counts.get(substance, 0) + 1
        if relation_type:
            relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1
        if returned_reasoning:
            returned_reasoning_counts[returned_reasoning] = returned_reasoning_counts.get(returned_reasoning, 0) + 1

    run_summary = {
        "run_dir": str(run_dir),
        "items_total": len(summary_rows),
        "items_ok": sum(1 for row in summary_rows if row["status"] == "ok"),
        "items_error": sum(1 for row in summary_rows if row["status"] == "error"),
        "items_skipped_existing": sum(1 for row in summary_rows if row["status"] == "skipped_existing"),
        "judgments_dir": str(judgments_dir),
        "api_backend": args.api_backend,
        "api_base_url": args.api_base_url,
        "api_key_slots": len(api_keys),
        "model": args.model,
        "requested_reasoning_effort": args.reasoning_effort,
        "returned_reasoning_counts": returned_reasoning_counts,
        "citation_substance_counts": citation_substance_counts,
        "relation_type_counts": relation_type_counts,
    }
    (run_dir / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
