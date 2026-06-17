import json
import pathlib


def load_attacks(path: str = "attacks/payloads.json") -> list[dict]:
    data = json.loads(pathlib.Path(path).read_text())
    return data["attacks"]
