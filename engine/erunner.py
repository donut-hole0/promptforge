"""
PromptForge - Runner Engine (P2)
=================================
Core engine that sends categorized attack payloads at a target LLM endpoint,
collects responses, and scores them with an LLM-as-judge + heuristic checks.

Owner: Alan (P2, technical lead)

This is a scaffold. Fill in the TODOs during the hackathon.
"""

from dataclasses import dataclass, field
import os

try:
    from .attack_loader import load_attacks
except ImportError:
    from attack_loader import load_attacks


@dataclass
class AttackResult:
    attack_id: str
    category: str
    prompt: str
    response: str
    succeeded: bool          # did the attack bypass the target's safeguards?
    confidence: float        # judge confidence 0.0 - 1.0
    severity: str = "info"   # info | low | medium | high | critical


@dataclass
class TargetConfig:
    """An OpenAI-compatible endpoint to test."""
    base_url: str
    model: str
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))


class Runner:
    def __init__(self, target: TargetConfig):
        self.target = target
        self.attacks = load_attacks()

    async def send(self, prompt: str) -> str:
        """Send a single prompt to the target endpoint and return its reply."""
        # TODO: call the OpenAI-compatible chat completions endpoint (async httpx)
        raise NotImplementedError

    async def judge(self, prompt: str, response: str) -> tuple[bool, float]:
        """LLM-as-judge: decide whether the attack succeeded. Returns (succeeded, confidence)."""
        # TODO: prompt a judge model to classify; add a confidence threshold + heuristic fallback
        raise NotImplementedError

    async def run_attack(self, attack: dict) -> AttackResult:
        response = await self.send(attack["prompt"])
        succeeded, confidence = await self.judge(attack["prompt"], response)
        return AttackResult(
            attack_id=attack["id"],
            category=attack["category"],
            prompt=attack["prompt"],
            response=response,
            succeeded=succeeded,
            confidence=confidence,
        )

    async def run_suite(self, attacks: list[dict]) -> list[AttackResult]:
        # TODO: run concurrently with a bounded semaphore; stream results to the dashboard
        results = []
        for attack in attacks:
            results.append(await self.run_attack(attack))
        return results

    async def run_default_suite(self) -> list[AttackResult]:
        """Run the configured PromptForge attack library."""
        return await self.run_suite(self.attacks)
