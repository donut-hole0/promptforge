"""
PromptForge - FastAPI Server (P2)
===================================
Exposes three endpoints consumed by P3's dashboard:

  POST /api/start           — kick off a scan, returns scan_id
  GET  /api/stream/{id}     — SSE stream of AttackResult events
  GET  /api/report/{id}     — final aggregated report JSON

Owner: Alan (P2, technical lead)
"""

import asyncio
import json
import os
import uuid
from collections import defaultdict
from dataclasses import asdict

# Use the OS (Windows) trust store for TLS verification. Required when outbound
# HTTPS is intercepted by a corporate/AV proxy whose root CA lives in the Windows
# certificate store but not in certifi's bundle — the case on this machine.
# Must run before any library (httpx/google-genai/openai/anthropic) opens a connection.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass  # Windows-only; safe to skip on Mac/Linux

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from engine.attack_loader import load_attacks
from engine.runner import AttackResult, Runner, TargetConfig

load_dotenv()

app = FastAPI(title="PromptForge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory scan store: scan_id -> list of completed AttackResults
# An asyncio.Queue per scan is used to stream results to the SSE endpoint.
_scan_results: dict[str, list[AttackResult]] = {}
_scan_queues: dict[str, asyncio.Queue] = {}
_scan_complete: dict[str, bool] = {}
_scan_targets: dict[str, TargetConfig] = {}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class StartRequest(BaseModel):
    provider: str       # "anthropic" | "openai" | "google"
    model: str
    system_prompt: str = "You are a helpful assistant."


class StartResponse(BaseModel):
    scan_id: str
    attack_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_key_for(provider: str) -> str:
    if provider == "ollama":
        return "ollama"  # litellm needs a non-empty string; Ollama itself needs no key
    mapping = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    key = os.getenv(mapping.get(provider, ""), "")
    if not key:
        raise HTTPException(status_code=400, detail=f"No API key set for provider '{provider}'")
    return key


def _build_report(scan_id: str, target: TargetConfig) -> dict:
    results = _scan_results.get(scan_id, [])
    total = len(results)
    succeeded = sum(1 for r in results if r.succeeded)

    by_category: dict[str, dict] = defaultdict(lambda: {"succeeded": 0, "total": 0})
    for r in results:
        by_category[r.category]["total"] += 1
        if r.succeeded:
            by_category[r.category]["succeeded"] += 1

    risk_score = round((succeeded / total) * 100) if total else 0

    return {
        "scan_id": scan_id,
        "target": {"provider": target.provider, "model": target.model},
        "risk_score": risk_score,
        "total_attacks": total,
        "succeeded": succeeded,
        "failed": total - succeeded,
        "by_category": dict(by_category),
        "results": [asdict(r) for r in results],
    }


# ---------------------------------------------------------------------------
# Background task that runs attacks and feeds the queue
# ---------------------------------------------------------------------------

async def _run_scan(scan_id: str, target: TargetConfig, attacks: list[dict]):
    queue = _scan_queues[scan_id]
    runner = Runner(target)
    try:
        async for result in runner.run_suite(attacks):
            _scan_results[scan_id].append(result)
            await queue.put(result)
    finally:
        _scan_complete[scan_id] = True
        await queue.put(None)  # sentinel — tells the SSE generator to close


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/start", response_model=StartResponse)
async def start_scan(req: StartRequest):
    api_key = _api_key_for(req.provider)
    target = TargetConfig(
        provider=req.provider,
        model=req.model,
        system_prompt=req.system_prompt,
        api_key=api_key,
    )
    attacks = load_attacks()
    scan_id = str(uuid.uuid4())
    _scan_results[scan_id] = []
    _scan_queues[scan_id] = asyncio.Queue()
    _scan_complete[scan_id] = False
    _scan_targets[scan_id] = target

    asyncio.create_task(_run_scan(scan_id, target, attacks))
    return StartResponse(scan_id=scan_id, attack_count=len(attacks))


@app.get("/api/stream/{scan_id}")
async def stream_results(scan_id: str):
    if scan_id not in _scan_queues:
        raise HTTPException(status_code=404, detail="Scan not found")

    queue = _scan_queues[scan_id]

    async def event_generator():
        while True:
            result: AttackResult | None = await queue.get()
            if result is None:
                break
            payload = json.dumps(asdict(result))
            yield f"data: {payload}\n\n"
        yield "data: {\"event\": \"done\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/report/{scan_id}")
async def get_report(scan_id: str):
    if scan_id not in _scan_results:
        raise HTTPException(status_code=404, detail="Scan not found")
    if not _scan_complete.get(scan_id):
        raise HTTPException(status_code=202, detail="Scan still running")

    target = _scan_targets[scan_id]
    return _build_report(scan_id, target)


# ---------------------------------------------------------------------------
# Entrypoint — `python server.py` starts the engine on :8000 (override with PORT)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
