# PromptForge Project Structure

```
promptforge/
├── attacks/                 # P1: Attack payload library
│   ├── payloads.json       # Hand-curated payloads (21 attacks)
│   ├── jbb_payloads.json   # JailbreakBench imports (83 attacks)
│   ├── load.py             # Loader utility
│   └── import_jbb.py       # Import script for JailbreakBench
│
├── engine/                  # P2: Backend execution engine
│   ├── runner.py           # Main runner: send attacks, judge responses
│   ├── attack_loader.py    # Attack loader with validation
│   ├── requirements.txt    # Engine dependencies
│   └── erunner.py          # (deprecated scaffold, not used)
│
├── dashboard/              # P3: real-time dashboard
│   ├── app.py             # ACTIVE: FastAPI server — serves the UI + proxies
│   │                      #   to the engine (mock fallback when engine offline)
│   ├── static/
│   │   └── index.html     # ACTIVE: single-file dashboard UI (Tailwind + JS)
│   └── src/               # DEPRECATED: earlier React/Vite prototype, unused
│       ├── App.tsx        #   (kept for reference; not wired into startup)
│       ├── App.css
│       ├── main.tsx
│       └── index.css
│
├── demo_bot/               # Demo: Intentionally vulnerable FastAPI chatbot
│   ├── vulnerable_bot.py  # Weak bot for live demo (direct prompt injection)
│   ├── requirements.txt   # FastAPI, Ollama client
│   └── README.md          # Demo setup instructions
│
├── server.py              # P2: FastAPI server
│   ├── POST /api/start    # Kick off a scan
│   ├── GET /api/stream/{id} # SSE stream of results
│   └── GET /api/report/{id} # Final aggregated report
│
├── requirements.txt       # Main dependencies
├── .env.example          # Environment variable template
├── .env                  # (local, not in git) actual API keys
├── .gitignore           # Never commit .env or __pycache__
├── README.md            # Project docs
├── start.sh             # Linux/Mac startup
├── start.cmd            # Windows startup
└── .git/                # Git repo
```

## How It All Works

1. **Backend (`server.py` + `engine/runner.py`):**
   - Receives a target config: provider, model, system prompt
   - Loads 100+ attack payloads from `attacks/`
   - Sends each attack concurrently to the target model
   - Uses LLM-as-judge (Gemini Flash) to score each response
   - Streams results via SSE to the dashboard
   - Generates final report with risk score, breakdown by category, successful attack samples

2. **Dashboard (`dashboard/app.py` + `dashboard/static/index.html`):**
   - FastAPI server on http://localhost:8050 that serves a single-file UI and
     proxies API calls to the engine (with a local mock fallback when offline)
   - Config form to select provider, model, system prompt
   - Live results grid showing attacks as red (succeeded) or green (failed)
   - Final report with:
     - Overall risk score
     - Category breakdown (bar charts)
     - Sample transcripts of successful attacks
     - Export to JSON

3. **Attack Library (`attacks/payloads.json` + `jbb_payloads.json`):**
   - 104 total payloads across categories:
     - **direct_injection**: direct override attempts
     - **jailbreak**: role-play, persona jailbreaks
     - **prompt_extraction**: system prompt disclosure
     - **indirect_injection**: fake system messages, context confusion, authority impersonation
     - **obfuscation**: base64 encoding, hidden instructions
   - Each has a `success_signal` for heuristic judging

4. **Demo Target (`demo_bot/vulnerable_bot.py`):**
   - Intentionally weak FastAPI bot running on http://localhost:9000
   - Direct concatenation of system prompt + user message (no protection)
   - Connected to local Ollama (`qwen3:4b`)
   - Used for live demo where judges watch PromptForge test it in real-time

## Setup & Execution

### Prerequisites
- Python 3.11+
- Node.js 18+
- API keys (Anthropic, OpenAI, or Google)
- Optional: Ollama + `qwen3:4b` (for demo target)

### 1. Clone & install backend
```bash
git clone https://github.com/donut-hole0/promptforge.git
cd promptforge

# Backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r engine/requirements.txt

# Setup env
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start everything

**Linux/Mac:**
```bash
./start.sh
```

**Windows:**
```cmd
start.cmd
```

Or manually:
```bash
# Terminal 1: Engine
python server.py

# Terminal 2: Dashboard
python -m uvicorn dashboard.app:app --port 8050

# Terminal 3 (optional): Demo target
cd demo_bot
pip install -r requirements.txt
uvicorn vulnerable_bot:app --reload --port 9000
```

> The dashboard runs fine on its own — if the engine is offline it falls back to
> a local mock generator so the UI still demos. Start the engine for real scans.

### 3. Use it
- Engine:    http://localhost:8000 (FastAPI server)
- Dashboard: http://localhost:8050
- API Docs:  http://localhost:8000/docs
- Demo bot:  http://localhost:9000 (optional, separate target)

## For Live Demo (Hackathon)

1. Have backend + dashboard running
2. Open dashboard in projector
3. Configure to target the demo_bot (or a real frontier model if you have API keys)
4. Hit "Start Scan"
5. Watch attacks stream in live (red = succeeded, green = failed)
6. Final report shows vulnerability summary
7. Judges see real-time attack results against a well-known AI model

## Architecture Decisions

- **Two-layer judge:** Heuristic check first (fast), LLM judge fallback (accurate)
- **Async concurrency:** 5-worker semaphore to avoid overwhelming target API
- **SSE streaming:** Real-time dashboard updates without polling
- **Modular payload library:** Easy to add more attacks, JailbreakBench imports
- **No key material in frontend:** All API keys server-side only, via env vars
- **Intentional demo weakness:** Demo bot has NO protections, guarantees visible attack success

## Security Notes

- **API keys:** Store in `.env`, never commit to git. `.gitignore` prevents accidents.
- **Spending caps:** Set on provider dashboards (Anthropic, OpenAI, Google) before running.
- **Test content:** Uses fake/dummy secrets, not harmful real-world targets.
- **Ethical:** Only test endpoints you own or have explicit permission to test.
