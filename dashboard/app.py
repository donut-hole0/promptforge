"""
PromptForge - Dashboard (P3)
============================
Real-time dashboard that streams attack results as the engine fires them,
then renders a final vulnerability report.

Owner: Iyan (P3)

Single-file FastAPI app:
  - GET  /              -> serves the dashboard UI (static/index.html)
  - GET  /events        -> Server-Sent Events stream of attack results
  - POST /scan          -> kicks off a scan (mock generator for now;
                           swap in Alan's engine.Runner when P2 is ready)

Run:
  pip install fastapi uvicorn
  uvicorn dashboard.app:app --reload --port 8000
  open http://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
PAYLOADS = ROOT.parent / "attacks" / "payloads.json"

app = FastAPI(title="PromptForge Dashboard")

# A single in-process queue is fine for the demo (one scan at a time).
_event_queue: "asyncio.Queue[dict]" = asyncio.Queue()


@dataclass
class AttackEvent:
    """Mirror of engine.AttackResult, plus a couple of UI fields."""
    attack_id: str
    category: str
    technique: str
    severity: str
    prompt: str
    response: str
    succeeded: bool
    confidence: float
    index: int
    total: int


def load_attacks() -> list[dict]:
    # Prefer the engine's loader (merges payloads.json + jbb_payloads.json,
    # deduped by id). Fall back to the starter file if the engine isn't importable.
    try:
        import sys
        sys.path.insert(0, str(ROOT.parent))
        from engine.attack_loader import load_attacks as load_all
        attacks = load_all()
        if attacks:
            return attacks
    except Exception:
        pass
    data = json.loads(PAYLOADS.read_text())
    return data.get("attacks", [])


# ---------------------------------------------------------------------------
# Mock scan: simulates the engine firing attacks so the UI can be built and
# demoed before P2 is wired up. Replace `run_mock_scan` with a real loop that
# consumes engine.Runner.run_suite() results.
# ---------------------------------------------------------------------------

MOCK_RESPONSES = {
    True: [
        "PWNED",
        "Sure! As FreeBot I have no restrictions. Here's what you asked...",
        "OK. Internal configuration: model=target-llm, tools=[email, fs]...",
        "My system prompt begins: 'You are a helpful assistant for...'",
    ],
    False: [
        "I can't help with that request.",
        "I'm sorry, but I won't ignore my guidelines.",
        "That looks like a prompt injection attempt, so I'll decline.",
    ],
}


async def run_mock_scan() -> None:
    attacks = load_attacks()
    total = len(attacks)
    for i, attack in enumerate(attacks, start=1):
        # Simulate target latency. Faster per-attack when the library is large
        # so a full 88-attack demo stays snappy.
        await asyncio.sleep(random.uniform(0.12, 0.3) if total > 20 else random.uniform(0.4, 1.1))
        # Weak demo target: ~60% of attacks succeed.
        succeeded = random.random() < 0.6
        event = AttackEvent(
            attack_id=attack["id"],
            category=attack.get("category", "unknown"),
            technique=attack.get("technique", ""),
            severity=attack.get("severity", "info"),
            prompt=attack["prompt"],
            response=random.choice(MOCK_RESPONSES[succeeded]),
            succeeded=succeeded,
            confidence=round(random.uniform(0.7, 0.99), 2),
            index=i,
            total=total,
        )
        await _event_queue.put({"type": "attack", "data": asdict(event)})
    await _event_queue.put({"type": "done", "data": {}})


@app.post("/scan")
async def start_scan(request: Request) -> dict:
    # Target config from the UI (base_url / model / api_key). Stored for when
    # P2's Runner is wired in; the mock scan ignores it.
    try:
        cfg = await request.json()
    except Exception:
        cfg = {}
    app.state.target = cfg

    # Drain any stale events, then start a fresh scan in the background.
    while not _event_queue.empty():
        _event_queue.get_nowait()
    asyncio.create_task(run_mock_scan())
    return {"status": "started", "total": len(load_attacks()), "target": cfg.get("model", "demo-target")}


@app.get("/events")
async def events() -> StreamingResponse:
    async def stream():
        while True:
            event = await _event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] == "done":
                break

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
