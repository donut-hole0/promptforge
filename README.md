# PromptForge

**An automated penetration-testing platform for AI agents.**

Point PromptForge at any LLM chatbot, agent, or API endpoint and it runs a curated battery of prompt-injection and jailbreak attacks, then generates a vulnerability report with severity scoring. Think "Burp Suite / Nessus, but for AI agents."

Built for CipherHacks.

> **Scope & honesty note:** PromptForge is a *measurement* tool. It does not claim to solve prompt injection (an open, likely-unsolvable problem). It measures how vulnerable a given AI endpoint is to known attack classes.

## How it works

1. You provide a target: an OpenAI-compatible API endpoint (or a chatbot wrapper).
2. The runner engine fires categorized attack payloads at the target.
3. Each response is scored pass/fail by an LLM-as-judge plus heuristic checks.
4. A dashboard streams results live and produces a CVSS-style report.

## Repository structure

```
attacks/      # P1 - curated + categorized attack payload library (JSON/YAML)
engine/       # P2 - runner engine: sends attacks, parses + scores responses
dashboard/    # P3 - real-time UI: live results, severity scoring, report export
demo-target/  # P4 - deliberately weak demo chatbot used for the live demo
docs/         # pitch deck, demo script, methodology notes
```

## Team & roles

| Role | Owner   | Responsibility                                                        |
|------|---------|----------------------------------------------------------------------|
| P1   | Shourya | Attack library: curate + categorize 100+ injection payloads          |
| P2   | Alan    | Runner engine + technical lead: execution pipeline, LLM-as-judge     |
| P3   | Iyan    | Dashboard: live results UI, severity scoring, report export          |
| P4   | Josh    | Demo target + pitch; floats to help on engine (P2) and dashboard (P3)|

## Tech stack

- **Engine:** Python 3.11 + FastAPI (async attack execution, REST API)
- **Scoring:** LLM-as-judge via API + regex/heuristic checks
- **Dashboard:** FastAPI serving a single-file HTML/JS UI, live updates over SSE
- **Demo target:** small FastAPI chatbot with an intentionally weak system prompt

## Getting started

```bash
git clone https://github.com/donut-hole0/promptforge.git
cd promptforge

# engine
cd engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Set your model API key as an environment variable (never commit keys):

```bash
export LLM_API_KEY=your_key_here
```

## Roadmap (24h hackathon)

- [ ] Engine can hit an OpenAI-compatible endpoint and return raw responses
- [ ] Attack library v1 (50+ payloads, categorized)
- [ ] LLM-as-judge scoring with confidence threshold
- [ ] Dashboard streams live results
- [ ] Demo target chatbot deployed
- [ ] Report export (PDF/JSON)
- [ ] Rehearsed live demo

## Importing JailbreakBench prompts

PromptForge can import public JailbreakBench artifacts into the local attack
library format. This keeps the backend on the same `attacks` schema while
letting the team refresh research-backed jailbreak payloads during the
hackathon.

```bash
pip install -r engine/requirements.txt
python attacks/import_jbb.py --jbb-artifact --method PAIR --model-name vicuna-13b-v1.5
```

That writes `attacks/jbb_payloads.json`. The engine loads both
`attacks/payloads.json` and `attacks/jbb_payloads.json` automatically when the
generated file exists.

To import a downloaded Hugging Face CSV/JSON export instead:

```bash
python attacks/import_jbb.py --input-file path/to/JBB-Behaviors.csv --prompt-field prompt
```

## Disclaimer

For educational and authorized security testing only. Only test endpoints you own or have explicit permission to test.
