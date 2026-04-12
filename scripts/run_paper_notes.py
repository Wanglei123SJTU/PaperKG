import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    render_template,
    repo_root,
    resolve_api_key,
    response_to_json_dict,
    sanitize_filename,
    save_cache,
    usage_summary,
    write_csv_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/jmr_2000_2025/paper_notes/manifest.csv")
    parser.add_argument("--prompt", default="prompts/paper_note_v1.md")
    parser.add_argument("--schema", default="schemas/paper_note_v1.schema.json")
    parser.add_argument("--out-root", default="data/jmr_2000_2025/paper_notes/runs")
    parser.add_argument("--file-cache", default="data/jmr_2000_2025/openai_file_cache.json")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-output-tokens", type=int, default=1400)
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
    parser.add_argument("--api-key", default="")
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
    notes_dir = run_dir / "notes"
    responses_dir = run_dir / "responses"
    errors_dir = run_dir / "errors"
    run_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)
    errors_dir.mkdir(parents=True, exist_ok=True)

    system_prompt, user_template = load_prompt_sections(prompt_path)
    schema = load_json(schema_path)
    schema_name = schema.get("title", "paper_note_v1").replace(" ", "_").lower()
    manifest_rows = load_csv_rows(manifest_path)

    if args.offset:
        manifest_rows = manifest_rows[args.offset :]
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
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    client = None
    cache: dict[str, dict[str, object]] = {}
    api_key = resolve_api_key(args.api_key or None)
    if args.api_backend == "openai_client":
        client = make_client(api_key=api_key, base_url=args.api_base_url or None)
        cache = load_cache(cache_path)

    summary_rows: list[dict[str, object]] = []
    summary_fields = [
        "paper_id",
        "status",
        "response_id",
        "model",
        "requested_reasoning_effort",
        "returned_reasoning_effort",
        "output_path",
        "raw_response_path",
        "error_path",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "error",
    ]

    def process_row(row: dict[str, str]) -> dict[str, object]:
        paper_id = row.get("paper_id") or sanitize_filename(row.get("resolved_doi") or row.get("query_doi") or row.get("title") or "paper")
        note_path = notes_dir / f"{paper_id}.json"
        response_path = responses_dir / f"{paper_id}.json"
        error_path = errors_dir / f"{paper_id}.txt"

        if args.skip_existing and note_path.exists():
            return {
                "paper_id": paper_id,
                "status": "skipped_existing",
                "response_id": "",
                "model": args.model,
                "requested_reasoning_effort": args.reasoning_effort,
                "returned_reasoning_effort": "",
                "output_path": str(note_path),
                "raw_response_path": str(response_path) if response_path.exists() else "",
                "error_path": str(error_path) if error_path.exists() else "",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "error": "",
            }

        try:
            pdf_path = (root / row["pdf_path"]).resolve()
            user_prompt = render_template(user_template, "{{paper_metadata_json}}", row)

            if args.api_backend == "openai_client":
                assert client is not None
                file_id = ensure_uploaded_pdf(client, pdf_path, cache, cache_path)
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
            else:
                response = invoke_structured_pdf_task_http(
                    api_key=api_key,
                    base_url=args.api_base_url,
                    model=args.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    pdf_paths=[pdf_path],
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
            note_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            response_dict = response_to_json_dict(response)
            response_path.write_text(json.dumps(response_dict, ensure_ascii=False, indent=2), encoding="utf-8")
            usage = usage_summary(response)
            returned_reasoning_effort = ""
            if isinstance(response_dict, dict):
                returned_reasoning_effort = str((response_dict.get("reasoning") or {}).get("effort") or "")

            return {
                "paper_id": paper_id,
                "status": "ok",
                "response_id": str(response_dict.get("id", "")),
                "model": args.model,
                "requested_reasoning_effort": args.reasoning_effort,
                "returned_reasoning_effort": returned_reasoning_effort,
                "output_path": str(note_path),
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
                "paper_id": paper_id,
                "status": "error",
                "response_id": "",
                "model": args.model,
                "requested_reasoning_effort": args.reasoning_effort,
                "returned_reasoning_effort": "",
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
            future_to_index = {executor.submit(process_row, row): idx for idx, row in enumerate(manifest_rows, start=1)}
            completed = 0
            for future in as_completed(future_to_index):
                completed += 1
                result = future.result()
                summary_rows.append(result)
                write_csv_rows(run_dir / "summary.csv", summary_fields, summary_rows)
                print(f"{completed}/{total} {result['paper_id']}")
    else:
        for index, row in enumerate(manifest_rows, start=1):
            result = process_row(row)
            summary_rows.append(result)
            write_csv_rows(run_dir / "summary.csv", summary_fields, summary_rows)
            print(f"{index}/{total} {result['paper_id']}")
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    if args.api_backend == "openai_client":
        save_cache(cache_path, cache)

    run_summary = {
        "run_dir": str(run_dir),
        "items_total": len(summary_rows),
        "items_ok": sum(1 for row in summary_rows if row["status"] == "ok"),
        "items_error": sum(1 for row in summary_rows if row["status"] == "error"),
        "items_skipped_existing": sum(1 for row in summary_rows if row["status"] == "skipped_existing"),
        "notes_dir": str(notes_dir),
        "api_backend": args.api_backend,
        "model": args.model,
        "requested_reasoning_effort": args.reasoning_effort,
    }
    (run_dir / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
