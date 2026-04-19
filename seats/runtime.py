# Seat Runtime - LLM-backed seat execution layer

import json
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

import requests

SEAT_RUNTIME_MODES = ["simulation", "local_llm", "hybrid"]


@dataclass
class SeatConfig:
    seat_id: str
    role: str
    model: str = "qwen3:8b"
    temperature: float = 0.7
    max_tokens: int = 512
    timeout: int = 30
    enabled: bool = True
    tier: str = "hot"  # hot or cold


@dataclass
class SeatResponse:
    seat: str
    node_id: str
    stance: str  # support, object, neutral, abstain
    summary: str
    proposed_actions: List[Dict[str, str]] = field(default_factory=list)
    vote_position: str = "neutral"
    vote_reason: str = ""
    confidence: float = 0.5
    model_used: str = ""
    latency_ms: int = 0
    parse_failed: bool = False
    fallback_used: bool = False
    error: str = ""


DEFAULT_SEAT_CONFIGS = {
    "Strategist": SeatConfig("Strategist", "Strategist", "qwen3:8b", 0.7, tier="hot"),
    "Architect": SeatConfig("Architect", "Architect", "gemma3:4b", 0.6, tier="hot"),
    "Researcher": SeatConfig(
        "Researcher", "Researcher", "granite3.3:2b", 0.5, tier="hot"
    ),
    "Operator": SeatConfig("Operator", "Operator", "mistral:latest", 0.75, tier="hot"),
    "Skeptic": SeatConfig("Skeptic", "Skeptic", "phi4-mini", 0.6, tier="hot"),
    "Cold1": SeatConfig("Cold1", "Cold", "olmo2:7b", 0.5, tier="cold"),
    "Cold2": SeatConfig("Cold2", "Cold", "qwen3:14b", 0.5, tier="cold"),
}


class SeatRuntime:
    def __init__(
        self,
        mode: str = "simulation",
        configs: Dict[str, SeatConfig] = None,
        ollama_base: str = "http://localhost:11434",
    ):
        self.mode = mode
        self.ollama_base = ollama_base
        self.configs = configs or DEFAULT_SEAT_CONFIGS.copy()
        self._check_models()

    def _check_models(self) -> List[str]:
        """Check available models."""
        try:
            r = requests.get(f"{self.ollama_base}/api/tags", timeout=2)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except:
            pass
        return []

    def execute_seat(
        self,
        seat_id: str,
        node_context: str,
        system_prompt: str,
    ) -> SeatResponse:
        """Execute a seat with its configured model."""
        cfg = self.configs.get(seat_id)
        if not cfg or not cfg.enabled:
            return SeatResponse(
                seat=seat_id, node_id="", stance="abstain", summary="Seat disabled"
            )

        if self.mode == "simulation":
            return self._simulation_response(seat_id, node_context)
        elif self.mode == "local_llm":
            return self._llm_response(cfg, node_context, system_prompt)
        else:  # hybrid
            try:
                return self._llm_response(cfg, node_context, system_prompt)
            except Exception as e:
                return self._simulation_response(seat_id, node_context, fallback=True)

    def _llm_response(
        self,
        cfg: SeatConfig,
        node_context: str,
        system_prompt: str,
    ) -> SeatResponse:
        """Call local LLM."""
        import time

        start = time.time()

        prompt = f"{system_prompt}\n\nNode Context:\n{node_context}\n\nRespond with JSON only."

        try:
            r = requests.post(
                f"{self.ollama_base}/api/generate",
                json={
                    "model": cfg.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": cfg.temperature,
                        "num_predict": cfg.max_tokens,
                    },
                },
                timeout=cfg.timeout,
            )
            latency = int((time.time() - start) * 1000)

            if r.status_code != 200:
                raise RuntimeError(f"Ollama error: {r.status_code}")

            output = r.json().get("response", "").strip()

            # Try to parse JSON
            try:
                # Find JSON in output
                if "```json" in output:
                    output = output.split("```json")[1].split("```")[0]
                elif "{" in output:
                    start = output.find("{")
                    end = output.rfind("}") + 1
                    output = output[start:end]

                data = json.loads(output)
                return SeatResponse(
                    seat=data.get("seat", cfg.seat_id),
                    node_id=data.get("node_id", ""),
                    stance=data.get("stance", "neutral"),
                    summary=data.get("summary", "")[:200],
                    proposed_actions=data.get("proposed_actions", []),
                    vote_position=data.get("vote", {}).get("position", "neutral"),
                    vote_reason=data.get("vote", {}).get("reason", "")[:100],
                    confidence=data.get("confidence", 0.5),
                    model_used=cfg.model,
                    latency_ms=latency,
                )
            except json.JSONDecodeError:
                return SeatResponse(
                    seat=cfg.seat_id,
                    node_id="",
                    stance="neutral",
                    summary=output[:200],
                    parse_failed=True,
                    model_used=cfg.model,
                    latency_ms=latency,
                    error=f"Parse failed: {output[:100]}",
                )

        except requests.exceptions.Timeout:
            return SeatResponse(
                seat=cfg.seat_id,
                node_id="",
                stance="abstain",
                summary="Timeout",
                error=f"Timeout after {cfg.timeout}s",
                model_used=cfg.model,
            )
        except Exception as e:
            return SeatResponse(
                seat=cfg.seat_id,
                node_id="",
                stance="abstain",
                summary="Model unavailable",
                error=str(e),
                model_used=cfg.model,
                fallback_used=(self.mode == "hybrid"),
            )

    def _simulation_response(
        self,
        seat_id: str,
        node_context: str,
        fallback: bool = False,
    ) -> SeatResponse:
        """Fallback simulation response."""
        # Simple heuristic responses for simulation mode
        stance_map = {
            "Strategist": ("support", 0.7),
            "Architect": ("support", 0.65),
            "Researcher": ("neutral", 0.55),
            "Operator": ("support", 0.75),
            "Skeptic": ("object", 0.6),
        }
        stance, conf = stance_map.get(seat_id, ("neutral", 0.5))

        return SeatResponse(
            seat=seat_id,
            node_id=node_context[:20] if node_context else "",
            stance=stance,
            summary=f"[SIM] {seat_id} response to topic",
            confidence=conf,
            fallback_used=fallback,
        )


def build_seat_prompt(
    seat: str, node_title: str, node_summary: str, history: str = ""
) -> str:
    """Build prompt for seat."""
    base = f"""You are {seat}. Analyze this node and respond with JSON.

Node: {node_title}
Summary: {node_summary}
{history}

JSON schema:
{{
  "seat": "{seat}",
  "node_id": "auto",
  "stance": "support|object|neutral|abstain",
  "summary": "one short explanation",
  "proposed_actions": [{{"action_type": "", "title": "", "summary": ""}}],
  "vote": {{"position": "support|challenge|neutral|abstain", "reason": ""}},
  "confidence": 0.0-1.0
}}

Respond with JSON only, no markdown."""
    return base
