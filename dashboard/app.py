"""
PromptForge - Dashboard (P3)
============================
FastAPI server that serves the real-time dashboard UI.

Talks to the real engine (server.py on port 8000) when available,
falls back to a mock generator for offline development.

Endpoints:
  GET  /                       -> dashboard UI
  POST /api/start              -> proxied to server.py (or mock)
  GET  /api/stream/{scan_id}   -> proxied to server.py (or mock)
  GET  /api/report/{scan_id}   -> proxied to server.py (or mock)
  GET  /api/health             -> check if server.py is reachable

Run (dashboard only, mock mode):
  pip install fastapi uvicorn httpx
  uvicorn dashboard.app:app --reload --port 8050

Run (full stack):
  python server.py                         # terminal 1 (port 8000)
  uvicorn dashboard.app:app --port 8050    # terminal 2
"""

from __future__ import annotations

# Verify TLS against the OS trust store (corporate/AV proxies intercept HTTPS
# with a root CA that lives in the Windows store but not certifi). Must run
# before openai/google clients open a connection.
import truststore
truststore.inject_into_ssl()

import asyncio
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse

from engine.runner import Runner, TargetConfig

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
PAYLOADS = ROOT.parent / "attacks" / "payloads.json"

app = FastAPI(title="PromptForge Dashboard")


# ---------------------------------------------------------------------------
# Attack library (mock fallback only)
# ---------------------------------------------------------------------------

def load_attacks() -> list[dict]:
    try:
        import sys
        sys.path.insert(0, str(ROOT.parent))
        from engine.attack_loader import load_attacks as load_all
        attacks = load_all()
        if attacks:
            return attacks
    except Exception:
        pass
    p = ROOT.parent / "attacks" / "payloads.json"
    if p.exists():
        return json.loads(p.read_text()).get("attacks", [])
    return []


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def engine_is_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            r = await client.get(f"{ENGINE_URL}/docs")
            return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Mock scan: simulates the engine firing attacks so the UI can be built and
# demoed before P2 is wired up. Replace `run_mock_scan` with a real loop that
# consumes engine.Runner.run_suite() results.
# ---------------------------------------------------------------------------

@dataclass
class MockResult:
    attack_id: str
    category: str
    technique: str
    severity: str
    prompt: str
    response: str
    succeeded: bool
    confidence: float
    reason: str = ""


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


@app.get("/api/health")
async def health():
    up = await engine_is_up()
    return {"engine": "up" if up else "offline", "mode": "live" if up else "mock"}


@app.post("/api/start")
async def start_scan(request: Request):
    body = await request.body()

    if await engine_is_up():
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{ENGINE_URL}/api/start",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            return r.json()

    payload = json.loads(body) if body else {}
    attacks = load_attacks()
    scan_id = str(uuid.uuid4())
    _mock_queues[scan_id] = asyncio.Queue()
    _mock_results[scan_id] = []
    _mock_complete[scan_id] = False
    asyncio.create_task(_run_mock_scan(scan_id, attacks))
    return {"scan_id": scan_id, "attack_count": len(attacks), "mode": "mock", "target": payload.get("model", "demo")}


@app.get("/api/stream/{scan_id}")
async def stream_results(scan_id: str):
    if await engine_is_up():
        async def proxy_stream():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", f"{ENGINE_URL}/api/stream/{scan_id}") as r:
                    async for chunk in r.aiter_text():
                        yield chunk
        return StreamingResponse(proxy_stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    if scan_id not in _mock_queues:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Scan not found")

    queue = _mock_queues[scan_id]

    async def mock_stream():
        while True:
            result = await queue.get()
            if result is None:
                yield 'data: {"event": "done"}\n\n'
                break
            yield f"data: {json.dumps(result)}\n\n"

    return StreamingResponse(mock_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.get("/api/report/{scan_id}")
async def get_report(scan_id: str):
    if await engine_is_up():
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{ENGINE_URL}/api/report/{scan_id}")
            return r.json()

    results = _mock_results.get(scan_id, [])
    total = len(results)
    succeeded = sum(1 for r in results if r["succeeded"])
    by_category: dict = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"succeeded": 0, "total": 0}
        by_category[cat]["total"] += 1
        if r["succeeded"]:
            by_category[cat]["succeeded"] += 1

    return {
        "scan_id": scan_id,
        "target": {"provider": "mock", "model": "demo-target"},
        "risk_score": round((succeeded / total) * 100) if total else 0,
        "total_attacks": total,
        "succeeded": succeeded,
        "failed": total - succeeded,
        "by_category": by_category,
        "results": results,
    }
