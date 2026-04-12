import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from jsonschema import Draft202012Validator
from openai import OpenAI


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def now_run_name() -> str:
    return "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sanitize_filename(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-")
    return value or "item"


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip().strip("/")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    import csv

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def resolve_api_key(explicit_api_key: str | None = None) -> str:
    api_keys = resolve_api_keys([explicit_api_key] if explicit_api_key else None)
    if not api_keys:
        raise RuntimeError("OPENAI_API_KEY is not set in the current shell environment.")
    return api_keys[0]


def resolve_api_keys(explicit_api_keys: list[str] | None = None) -> list[str]:
    keys: list[str] = []
    if explicit_api_keys:
        keys.extend(value.strip() for value in explicit_api_keys if value and value.strip())
    if not keys:
        env_multi = os.environ.get("OPENAI_API_KEYS", "")
        if env_multi.strip():
            keys.extend(part.strip() for part in re.split(r"[\r\n,;]+", env_multi) if part.strip())
    if not keys:
        env_single = os.environ.get("OPENAI_API_KEY", "").strip()
        if env_single:
            keys.append(env_single)
    if not keys:
        raise RuntimeError("OPENAI_API_KEY or OPENAI_API_KEYS is not set in the current shell environment.")
    return keys


def load_prompt_sections(prompt_path: Path) -> tuple[str, str]:
    text = prompt_path.read_text(encoding="utf-8")
    system_prompt = extract_text_code_block(text, "System Prompt")
    user_template = extract_text_code_block(text, "User Prompt Template")
    return system_prompt, user_template


def extract_text_code_block(markdown: str, heading: str) -> str:
    pattern = rf"## {re.escape(heading)}\r?\n\r?\n```text\r?\n(.*?)\r?\n```"
    match = re.search(pattern, markdown, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Could not find ```text``` block under heading: {heading}")
    return match.group(1).strip()


def render_template(template: str, placeholder: str, payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    return template.replace(placeholder, rendered)


def make_client(*, api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    return OpenAI(api_key=resolve_api_key(api_key), base_url=base_url)


def load_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    if not cache_path.exists():
        return {}
    return json.loads(cache_path.read_text(encoding="utf-8"))


def save_cache(cache_path: Path, cache: dict[str, dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def ensure_uploaded_pdf(
    client: OpenAI,
    pdf_path: Path,
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
    *,
    wait_timeout_seconds: float = 1800.0,
) -> str:
    pdf_path = pdf_path.resolve()
    stat = pdf_path.stat()
    cache_key = str(pdf_path)
    cached = cache.get(cache_key)

    if cached and cached.get("size") == stat.st_size and cached.get("mtime_ns") == stat.st_mtime_ns and cached.get("file_id"):
        return str(cached["file_id"])

    with pdf_path.open("rb") as handle:
        file_obj = client.files.create(file=handle, purpose="user_data")
    client.files.wait_for_processing(file_obj.id, max_wait_seconds=wait_timeout_seconds)

    cache[cache_key] = {
        "file_id": file_obj.id,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    save_cache(cache_path, cache)
    return file_obj.id


def response_to_json_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    return json.loads(response.model_dump_json(indent=2))


def extract_output_text(response: Any) -> str:
    if isinstance(response, dict):
        texts: list[str] = []
        for item in response.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        texts.append(content.get("text", ""))
        return "".join(texts)
    return response.output_text


def extract_structured_payload(response: Any, schema: dict[str, Any]) -> dict[str, Any]:
    output_text = extract_output_text(response)
    if not output_text.strip():
        raise ValueError("Model returned empty output_text.")
    payload = json.loads(output_text)
    Draft202012Validator(schema).validate(payload)
    return payload


def usage_summary(response: Any) -> dict[str, int]:
    if isinstance(response, dict):
        usage = response.get("usage") or {}
        return {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }
    usage = getattr(response, "usage", None)
    if not usage:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def invoke_structured_pdf_task(
    client: OpenAI,
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    file_ids: list[str],
    schema_name: str,
    schema: dict[str, Any],
    temperature: float,
    max_output_tokens: int,
    reasoning_effort: str,
) -> Any:
    content: list[dict[str, str]] = [{"type": "input_text", "text": user_prompt}]
    content.extend({"type": "input_file", "file_id": file_id} for file_id in file_ids)

    return client.responses.create(
        model=model,
        instructions=system_prompt,
        input=[{"role": "user", "content": content}],
        temperature=temperature,
        truncation="auto",
        max_output_tokens=max_output_tokens,
        reasoning={"effort": reasoning_effort},
        text={
            "format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                },
            }
        },
    )


def pdf_to_data_uri(pdf_path: Path) -> str:
    encoded = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    return "data:application/pdf;base64," + encoded


def recover_partial_bytes(exc: Exception) -> bytes | None:
    for arg in getattr(exc, "args", []):
        if hasattr(arg, "partial"):
            return getattr(arg, "partial")
    return None


def is_transient_request_exception(exc: Exception) -> bool:
    text = repr(exc).lower()
    transient_markers = [
        "timed out",
        "timeout",
        "sslwantwriteerror",
        "connection aborted",
        "max retries exceeded",
        "incompleteread",
    ]
    return any(marker in text for marker in transient_markers)


def invoke_structured_pdf_task_http(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    pdf_paths: list[Path],
    schema_name: str,
    schema: dict[str, Any],
    temperature: float,
    max_output_tokens: int,
    reasoning_effort: str,
    connect_timeout_seconds: float = 180.0,
    timeout_seconds: float = 900.0,
    max_attempts: int = 4,
    initial_backoff_seconds: float = 2.0,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/responses"
    content: list[dict[str, str]] = [{"type": "input_text", "text": user_prompt}]
    content.extend(
        {
            "type": "input_file",
            "filename": pdf_path.name,
            "file_data": pdf_to_data_uri(pdf_path),
        }
        for pdf_path in pdf_paths
    )
    return invoke_structured_task_http(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        content=content,
        schema_name=schema_name,
        schema=schema,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
        connect_timeout_seconds=connect_timeout_seconds,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        initial_backoff_seconds=initial_backoff_seconds,
    )


def invoke_structured_text_task_http(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    temperature: float,
    max_output_tokens: int,
    reasoning_effort: str,
    connect_timeout_seconds: float = 180.0,
    timeout_seconds: float = 900.0,
    max_attempts: int = 4,
    initial_backoff_seconds: float = 2.0,
) -> dict[str, Any]:
    return invoke_structured_task_http(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        content=[{"type": "input_text", "text": user_prompt}],
        schema_name=schema_name,
        schema=schema,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
        connect_timeout_seconds=connect_timeout_seconds,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        initial_backoff_seconds=initial_backoff_seconds,
    )


def invoke_structured_task_http(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    content: list[dict[str, str]],
    schema_name: str,
    schema: dict[str, Any],
    temperature: float,
    max_output_tokens: int,
    reasoning_effort: str,
    connect_timeout_seconds: float = 180.0,
    timeout_seconds: float = 900.0,
    max_attempts: int = 4,
    initial_backoff_seconds: float = 2.0,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/responses"

    payload = {
        "model": model,
        "instructions": system_prompt,
        "input": [{"role": "user", "content": content}],
        "reasoning": {"effort": reasoning_effort},
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(connect_timeout_seconds, timeout_seconds),
                stream=True,
            )
            try:
                body = response.raw.read()
            except Exception as exc:  # noqa: BLE001
                partial = recover_partial_bytes(exc)
                if partial is None:
                    raise
                body = partial

            obj = json.loads(body.decode("utf-8", errors="replace"))
            if response.status_code >= 500 and attempt < max_attempts:
                time.sleep(initial_backoff_seconds * (2 ** (attempt - 1)))
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}: {json.dumps(obj, ensure_ascii=False)}")
            return obj
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_attempts or not is_transient_request_exception(exc):
                raise
            time.sleep(initial_backoff_seconds * (2 ** (attempt - 1)))

    assert last_exc is not None
    raise last_exc
