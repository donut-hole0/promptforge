"""
PromptForge - Dashboard (P3)
============================
FastAPI server that serves the real-time dashboard UI and bridges it to the
real engine.

It proxies the dashboard's API calls to the engine (server.py, default
http://127.0.0.1:8000). When the engine isn't running it falls back to a
local mock generator so the UI still works offline for development/demo.

Endpoints (mirror server.py so the UI speaks one API):
  GET  /                       -> dashboard UI
  GET  /api/health             -> is the engine reachable? (live vs mock)
  GET  /api/config             -> pre-fill API keys from .env
  POST /api/start              -> start a scan        (proxied, or mock)
  GET  /api/stream/{scan_id}   -> SSE result stream   (proxied, or mock)
  GET  /api/report/{scan_id}   -> final report JSON   (proxied, or mock)

Run (full stack — real scans):
  python -m uvicorn server:app --port 8000           # terminal 1 (engine)
  python -m uvicorn dashboard.app:app --port 8050    # terminal 2 (this UI)

Run (dashboard only, mock mode): just start this server; the engine being
offline triggers the mock fallback automatically.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

load_dotenv()

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
ENGINE_URL = os.getenv("ENGINE_URL", "http://127.0.0.1:8000").rstrip("/")

app = FastAPI(title="PromptForge Dashboard")

# Mock-fallback state, keyed by scan_id (only used when the engine is offline).
_mock_queues: dict[str, asyncio.Queue] = {}
_mock_results: dict[str, list[dict]] = {}
_mock_complete: dict[str, bool] = {}


# ---------------------------------------------------------------------------
# Attack library (mock fallback only — the real engine loads its own)
# ---------------------------------------------------------------------------

def load_attacks() -> list[dict]:
    """Prefer the engine's merged loader; fall back to the starter payloads."""
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
# Engine health
# ---------------------------------------------------------------------------

async def engine_is_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            r = await client.get(f"{ENGINE_URL}/docs")
            return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Mock scan: simulates engine output so the UI works without server.py.
# Emits AttackResult-shaped dicts matching server.py's schema.
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


async def _run_mock_scan(scan_id: str, attacks: list[dict]) -> None:
    queue = _mock_queues[scan_id]
    total = len(attacks)
    try:
        for attack in attacks:
            await asyncio.sleep(random.uniform(0.12, 0.3) if total > 20 else random.uniform(0.4, 1.0))
            succeeded = random.random() < 0.5
            result = {
                "attack_id": attack["id"],
                "category": attack.get("category", "unknown"),
                "technique": attack.get("technique", ""),
                "prompt": attack["prompt"],
                "response": random.choice(MOCK_RESPONSES[succeeded]),
                "succeeded": succeeded,
                "confidence": round(random.uniform(0.7, 0.99), 2),
                "severity": attack.get("severity", "info"),
                "reason": "mock result (engine offline)",
            }
            _mock_results[scan_id].append(result)
            await queue.put(result)
    finally:
        _mock_complete[scan_id] = True
        await queue.put(None)


def _mock_report(scan_id: str) -> dict:
    results = _mock_results.get(scan_id, [])
    total = len(results)
    succeeded = sum(1 for r in results if r["succeeded"])
    by_category: dict[str, dict] = {}
    for r in results:
        cat = r["category"]
        by_category.setdefault(cat, {"succeeded": 0, "total": 0})
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def landing() -> FileResponse:
    return FileResponse(STATIC / "landing.html")


@app.get("/app")
async def app_ui() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/forge-mark.svg")
async def forge_mark() -> FileResponse:
    return FileResponse(STATIC / "forge-mark.svg")


@app.get("/api/health")
async def health() -> dict:
    up = await engine_is_up()
    return {"engine": "up" if up else "offline", "mode": "live" if up else "mock"}


@app.get("/api/config")
async def config() -> dict:
    """Return API keys from .env so the UI can pre-fill the key field."""
    return {
        "google_api_key":    os.getenv("GOOGLE_API_KEY", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "openai_api_key":    os.getenv("OPENAI_API_KEY", ""),
    }


@app.post("/api/start")
async def start_scan(request: Request) -> dict:
    body = await request.body()
    payload = json.loads(body) if body else {}

    # If the UI sent an API key, inject it into env so litellm picks it up.
    if payload.get("api_key"):
        env_map = {"google": "GOOGLE_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
        if env_var := env_map.get(payload.get("provider", "")):
            os.environ[env_var] = payload["api_key"]

    # Live: forward to the real engine.
    if await engine_is_up():
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{ENGINE_URL}/api/start",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            return r.json()

    # Offline: run a local mock scan.
    attacks = load_attacks()
    count = payload.get("count", 0)
    if count and count > 0:
        attacks = attacks[:count]
    scan_id = str(uuid.uuid4())
    _mock_queues[scan_id] = asyncio.Queue()
    _mock_results[scan_id] = []
    _mock_complete[scan_id] = False
    asyncio.create_task(_run_mock_scan(scan_id, attacks))
    return {"scan_id": scan_id, "attack_count": len(attacks)}


@app.get("/api/stream/{scan_id}")
async def stream_results(scan_id: str) -> StreamingResponse:
    # Live: proxy the engine's SSE stream straight through.
    if await engine_is_up():
        async def proxy_stream():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", f"{ENGINE_URL}/api/stream/{scan_id}") as r:
                    async for chunk in r.aiter_raw():
                        yield chunk
        return StreamingResponse(
            proxy_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Offline: stream from the mock queue.
    if scan_id not in _mock_queues:
        raise HTTPException(status_code=404, detail="Scan not found")
    queue = _mock_queues[scan_id]

    async def mock_stream():
        while True:
            result = await queue.get()
            if result is None:
                yield 'data: {"event":"done"}\n\n'
                break
            yield f"data: {json.dumps(result)}\n\n"

    return StreamingResponse(
        mock_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/report/{scan_id}")
async def get_report(scan_id: str) -> dict:
    if await engine_is_up():
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{ENGINE_URL}/api/report/{scan_id}")
            return r.json()

    if scan_id not in _mock_results:
        raise HTTPException(status_code=404, detail="Scan not found")
    return _mock_report(scan_id)
