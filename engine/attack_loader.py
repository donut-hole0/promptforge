"""
Attack-library loading helpers for PromptForge.

The runner consumes a normalized list of attack dictionaries. Keeping file
loading here lets the attack library grow from hand-curated JSON, generated
JailbreakBench imports, or both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATTACK_FILES = (
    REPO_ROOT / "attacks" / "payloads.json",
    REPO_ROOT / "attacks" / "jbb_payloads.json",
)


REQUIRED_FIELDS = ("id", "category", "technique", "severity", "prompt")


def load_attack_file(path: str | Path) -> list[dict[str, Any]]:
    attack_path = Path(path)
    data = json.loads(attack_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("attacks"), list):
        raise ValueError(f"{attack_path} must contain an object with an 'attacks' list.")

    attacks = data["attacks"]
    for index, attack in enumerate(attacks, start=1):
        if not isinstance(attack, dict):
            raise ValueError(f"{attack_path} attack #{index} must be an object.")
        missing = [field for field in REQUIRED_FIELDS if not attack.get(field)]
        if missing:
            raise ValueError(
                f"{attack_path} attack #{index} is missing required fields: {', '.join(missing)}"
            )
    return attacks


def load_attacks(paths: Iterable[str | Path] | None = None) -> list[dict[str, Any]]:
    attack_paths = tuple(Path(path) for path in (paths or DEFAULT_ATTACK_FILES))
    attacks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for path in attack_paths:
        if not path.exists():
            continue
        for attack in load_attack_file(path):
            attack_id = str(attack["id"])
            if attack_id in seen_ids:
                continue
            seen_ids.add(attack_id)
            attacks.append(attack)

    return attacks
