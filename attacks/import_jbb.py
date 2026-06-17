"""
Import public JailbreakBench prompts into PromptForge's attack-library format.

This script supports two sources:
- The official jailbreakbench Python package, via jbb.read_artifact(...)
- A local CSV/JSON export, such as a downloaded Hugging Face dataset file

It intentionally prints counts and file paths, not the jailbreak prompt text.
Use only for authorized defensive testing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


DEFAULT_PROMPT_FIELDS = (
    "prompt",
    "jailbreak",
    "jailbreak_prompt",
    "attack",
    "attack_prompt",
    "text",
    "content",
)


def _slug(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "unknown"


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _as_prompt(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if hasattr(value, "prompt"):
        return str(value.prompt).strip()
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(), ensure_ascii=False, sort_keys=True).strip()
    if hasattr(value, "dict"):
        return json.dumps(value.dict(), ensure_ascii=False, sort_keys=True).strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True).strip()


def _attack_record(
    *,
    prompt: str,
    source: str,
    technique: str,
    index: int,
    model_name: str | None = None,
) -> dict[str, Any]:
    source_slug = _slug(source)
    technique_slug = _slug(technique)
    model_slug = _slug(model_name or "generic")
    return {
        "id": f"jbb-{technique_slug}-{model_slug}-{index:04d}-{_short_hash(prompt)}",
        "category": "jailbreak",
        "technique": f"JailbreakBench/{technique}",
        "severity": "high",
        "prompt": prompt,
        "success_signal": "",
        "source": {
            "name": source,
            "model_name": model_name,
            "prompt_hash": _short_hash(prompt),
        },
    }


def from_jailbreakbench_artifact(
    *, method: str, model_name: str, cache_dir: Path, limit: int | None = None
) -> list[dict[str, Any]]:
    try:
        import jailbreakbench as jbb
    except ImportError as exc:
        raise SystemExit(
            "The jailbreakbench package is not installed. Install it first, then rerun "
            "this script. Example: pip install jailbreakbench"
        ) from exc

    artifact = jbb.read_artifact(
        method=method,
        model_name=model_name,
        custom_cache_dir=cache_dir,
    )
    jailbreaks = getattr(artifact, "jailbreaks", None)
    if jailbreaks is None:
        raise SystemExit("JailbreakBench artifact did not expose a 'jailbreaks' list.")

    records = []
    for index, item in enumerate(jailbreaks, start=1):
        if limit is not None and len(records) >= limit:
            break
        prompt = _as_prompt(getattr(item, "prompt", item))
        if prompt:
            source_category = getattr(item, "category", None)
            source_behavior = getattr(item, "behavior", None)
            records.append(
                _attack_record(
                    prompt=prompt,
                    source="JailbreakBench/artifacts",
                    technique=method,
                    index=index,
                    model_name=model_name,
                )
            )
            if source_category:
                records[-1]["source"]["category"] = str(source_category)
            if source_behavior:
                records[-1]["source"]["behavior"] = str(source_behavior)
    return records


def _load_json_rows(path: Path) -> Iterable[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("attacks", "data", "rows", "examples"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        else:
            rows = [data]
    else:
        raise SystemExit(f"Unsupported JSON shape in {path}")

    for row in rows:
        if isinstance(row, dict):
            yield row
        else:
            yield {"prompt": row}


def _load_csv_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def from_local_file(
    *, input_file: Path, prompt_field: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    suffix = input_file.suffix.lower()
    if suffix == ".json":
        rows = _load_json_rows(input_file)
    elif suffix == ".csv":
        rows = _load_csv_rows(input_file)
    else:
        raise SystemExit("Only .csv and .json local imports are supported.")

    records = []
    for index, row in enumerate(rows, start=1):
        if limit is not None and len(records) >= limit:
            break

        field = prompt_field
        if field is None:
            field = next((candidate for candidate in DEFAULT_PROMPT_FIELDS if row.get(candidate)), None)
        if field is None or not row.get(field):
            continue

        prompt = _as_prompt(row[field])
        if prompt:
            technique = _as_prompt(row.get("method") or row.get("technique") or "JBB-Behaviors")
            records.append(
                _attack_record(
                    prompt=prompt,
                    source=input_file.name,
                    technique=technique,
                    index=index,
                    model_name=_as_prompt(row.get("model_name") or "generic"),
                )
            )
    return records


def load_existing_attacks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("attacks"), list):
        raise SystemExit(f"{path} is not a PromptForge attack-library JSON file.")
    return data["attacks"]


def dedupe_attacks(attacks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    seen_prompts: set[str] = set()
    unique = []
    for attack in attacks:
        attack_id = str(attack.get("id", ""))
        prompt = str(attack.get("prompt", ""))
        prompt_hash = _short_hash(prompt)
        if attack_id in seen_ids or prompt_hash in seen_prompts:
            continue
        seen_ids.add(attack_id)
        seen_prompts.add(prompt_hash)
        unique.append(attack)
    return unique


def write_library(
    *, output: Path, imported: list[dict[str, Any]], merge_existing: Path | None = None
) -> int:
    existing = load_existing_attacks(merge_existing) if merge_existing else []
    attacks = dedupe_attacks([*existing, *imported])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "_comment": (
                    "PromptForge attack library. Contains public JailbreakBench-derived "
                    "payloads for authorized defensive testing only."
                ),
                "version": "0.1.0",
                "attacks": attacks,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return len(attacks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import JailbreakBench prompts into PromptForge JSON format."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--jbb-artifact", action="store_true", help="Use jailbreakbench.read_artifact")
    source.add_argument("--input-file", type=Path, help="Local Hugging Face CSV/JSON export")
    parser.add_argument("--method", default="PAIR", help="JailbreakBench artifact method")
    parser.add_argument("--model-name", default="vicuna-13b-v1.5", help="JailbreakBench artifact model")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".cache" / "jailbreakbench",
        help="Project-local cache directory for downloaded JailbreakBench artifacts",
    )
    parser.add_argument("--prompt-field", help="Column/key to read from a local CSV/JSON file")
    parser.add_argument("--limit", type=int, help="Maximum prompts to import")
    parser.add_argument("--merge-existing", type=Path, help="Existing PromptForge payload file to merge")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("jbb_payloads.json"),
        help="Output PromptForge JSON file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.jbb_artifact:
        imported = from_jailbreakbench_artifact(
            method=args.method,
            model_name=args.model_name,
            cache_dir=args.cache_dir,
            limit=args.limit,
        )
    else:
        imported = from_local_file(
            input_file=args.input_file, prompt_field=args.prompt_field, limit=args.limit
        )

    written = write_library(output=args.output, imported=imported, merge_existing=args.merge_existing)
    print(f"Imported {len(imported)} JailbreakBench records.")
    print(f"Wrote {written} unique PromptForge attacks.")
    print(f"Wrote PromptForge attack library: {args.output}")


if __name__ == "__main__":
    main()
