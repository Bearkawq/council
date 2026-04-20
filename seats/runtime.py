# Seat Runtime - LLM-backed seat execution layer

import json
import re
import time
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
    fallback_reason: str = ""
    empty_output: bool = False
    timeout: bool = False
    error: str = ""


DEFAULT_SEAT_CONFIGS = {
    "Strategist": SeatConfig("Strategist", "Strategist", "qwen3:8b", 0.7, tier="hot"),
    "Architect": SeatConfig("Architect", "Architect", "gemma3:4b", 0.6, tier="hot"),
    "Researcher": SeatConfig(
        "Researcher", "Researcher", "granite3.3:2b", 0.5, tier="hot"
    ),
    "Operator": SeatConfig("Operator", "Operator", "mistral:latest", 0.75, tier="hot"),
    "Skeptic": SeatConfig("Skeptic", "Skeptic", "phi4-mini:latest", 0.6, tier="hot"),
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
        self._available_models = self._check_models()

    def _check_models(self) -> List[str]:
        """Check available models."""
        try:
            r = requests.get(f"{self.ollama_base}/api/tags", timeout=2)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except:
            pass
        return []

    def is_model_available(self, model: str) -> bool:
        return model in self._available_models

    @property
    def available_models(self) -> List[str]:
        return self._available_models

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
                resp = self._llm_response(cfg, node_context, system_prompt)
                if resp.error or resp.parse_failed or resp.empty_output:
                    # Fall back to simulation
                    sim = self._simulation_response(
                        seat_id, node_context, fallback=True
                    )
                    sim.fallback_reason = resp.error or (
                        "parse_failed" if resp.parse_failed else "empty_output"
                    )
                    return sim
                return resp
            except Exception as e:
                sim = self._simulation_response(seat_id, node_context, fallback=True)
                sim.fallback_reason = str(e)[:60]
                return sim

    def _extract_json(self, output: str) -> Optional[dict]:
        """Robustly extract JSON-like object from output and attempt to fix common errors.

        Attempts:
        - strip markdown fences
        - find first {..} block
        - fix trailing commas
        - replace single quotes with double quotes as a last resort
        - return None if parsing fails
        """
        if not output or not output.strip():
            return None

        out = output.strip()

        # Strip markdown fences if present
        if "```json" in out:
            out = out.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in out:
            out = out.split("```", 1)[1].split("```", 1)[0]

        # Try to find the first JSON object bounds
        if "{" in out and "}" in out:
            start = out.find("{")
            end = out.rfind("}")
            if end > start:
                candidate = out[start : end + 1]
            else:
                candidate = out
        else:
            candidate = out

        # Try direct parse
        try:
            return json.loads(candidate)
        except Exception:
            pass

        # Try to remove trailing commas in objects/arrays
        fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(fixed)
        except Exception:
            pass

        # As a last resort, naively convert single quotes to double quotes
        naive = candidate.replace("'", '"')
        try:
            return json.loads(naive)
        except Exception:
            return None

    def _llm_response(
        self,
        cfg: SeatConfig,
        node_context: str,
        system_prompt: str,
        retry: int = 0,
    ) -> SeatResponse:
        """Call local LLM with more robust retry and parsing strategies."""
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
                timeout=cfg.timeout if retry == 0 else min(cfg.timeout * 2, 120),
            )
            latency = int((time.time() - start) * 1000)

            if r.status_code != 200:
                raise RuntimeError(f"Ollama error: {r.status_code}")

            output = r.json().get("response", "")

            # Check empty output and attempt one gentle nudge
            if not output or not output.strip():
                if retry < 2:
                    # gentle nudge to encourage JSON output
                    corrective = f"{system_prompt}\n\nNode Context:\n{node_context}\n\nThe previous answer was empty. Please respond only with JSON that conforms to the schema."
                    return self._llm_response(cfg, node_context, corrective, retry=retry + 1)
                return SeatResponse(
                    seat=cfg.seat_id,
                    node_id="",
                    stance="neutral",
                    summary="Empty model output",
                    empty_output=True,
                    model_used=cfg.model,
                    latency_ms=latency,
                )

            # Try to parse JSON
            data = self._extract_json(output)
            if data is None and retry < 2:
                # Retry with corrective, progressively stricter prompts
                if retry == 0:
                    corrective = (
                        system_prompt
                        + "\n\nPrevious output was not valid JSON. Respond ONLY with a single JSON object exactly matching the required schema. No explanation."
                    )
                else:
                    corrective = (
                        f"Respond ONLY with this exact small schema: {{\"seat\": \"{cfg.seat_id}\", \"node_id\": \"auto\", \"stance\": \"neutral\", \"summary\": \"short\", \"confidence\": 0.5}}"
                    )
                return self._llm_response(cfg, node_context, corrective, retry=retry + 1)

            if data is None:
                # Attempt to parse freeform proposed actions from text
                proposed = self._parse_freeform_actions(output)
                if proposed:
                    return SeatResponse(
                        seat=cfg.seat_id,
                        node_id="",
                        stance="neutral",
                        summary=output[:200],
                        proposed_actions=proposed,
                        model_used=cfg.model,
                        latency_ms=latency,
                    )

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

            return SeatResponse(
                seat=data.get("seat", cfg.seat_id),
                node_id=data.get("node_id", ""),
                stance=self._normalize_stance(data.get("stance", "neutral")),
                summary=data.get("summary", "")[:200],
                proposed_actions=data.get("proposed_actions", []),
                vote_position=self._normalize_vote(
                    data.get("vote", {}).get("position", "neutral")
                ),
                vote_reason=data.get("vote", {}).get("reason", "")[:100],
                confidence=max(0.0, min(1.0, data.get("confidence", 0.5))),
                model_used=cfg.model,
                latency_ms=latency,
            )

        except requests.exceptions.Timeout:
            if retry < 1:
                # one quick retry with larger timeout
                return self._llm_response(cfg, node_context, system_prompt, retry=retry + 1)
            return SeatResponse(
                seat=cfg.seat_id,
                node_id="",
                stance="abstain",
                summary="Timeout",
                timeout=True,
                error=f"Timeout after {cfg.timeout}s",
                model_used=cfg.model,
            )
        except requests.exceptions.ConnectionError:
            return SeatResponse(
                seat=cfg.seat_id,
                node_id="",
                stance="abstain",
                summary="Model unavailable",
                error="Connection refused - is Ollama running?",
                model_used=cfg.model,
            )
        except Exception as e:
            return SeatResponse(
                seat=cfg.seat_id,
                node_id="",
                stance="abstain",
                summary="Model unavailable",
                error=str(e)[:80],
                model_used=cfg.model,
            )

    def _normalize_stance(self, stance: str) -> str:
        valid = {"support", "object", "neutral", "abstain"}
        return stance.lower() if stance.lower() in valid else "neutral"

    def _normalize_vote(self, vote: str) -> str:
        valid = {"support", "challenge", "neutral", "abstain"}
        return vote.lower() if vote.lower() in valid else "neutral"

    def _simulation_response(
        self,
        seat_id: str,
        node_context: str,
        fallback: bool = False,
    ) -> SeatResponse:
        """Fallback simulation response."""
        stance_map = {
            "Strategist": ("support", 0.7),
            "Architect": ("support", 0.65),
            "Researcher": ("neutral", 0.55),
            "Operator": ("support", 0.75),
            "Skeptic": ("object", 0.55),
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

    def _parse_freeform_actions(self, output: str) -> List[Dict[str, str]]:
        """Attempt to extract proposed actions from freeform text when JSON parsing fails.

        Looks for lines like:
        - claim: Title - summary
        - 1) claim: Title - summary
        """
        lines = output.splitlines()
        actions = []
        for ln in lines:
            m = re.search(r"(?:-|\d+\))\s*(claim|alternative|refinement|support|object|evidence_needed)\s*[:\-]\s*(.+)", ln, re.IGNORECASE)
            if m:
                a_type = m.group(1).lower()
                rest = m.group(2).strip()
                if " - " in rest:
                    title, summary = rest.split(" - ", 1)
                else:
                    parts = rest.split(". ", 1)
                    title = parts[0]
                    summary = parts[1] if len(parts) > 1 else ""
                actions.append({"action_type": a_type, "title": title.strip(), "summary": summary.strip()})
        return actions

    def get_telemetry(self) -> Dict[str, Any]:
        """Get runtime telemetry."""
        return {
            "mode": self.mode,
            "available_models": self._available_models,
            "seats": {
                sid: {
                    "model": cfg.model,
                    "enabled": cfg.enabled,
                    "tier": cfg.tier,
                    "available": self.is_model_available(cfg.model),
                }
                for sid, cfg in self.configs.items()
            },
        }


def build_normal_round_prompt(
    seat: str,
    seat_profile: Any,
    node_title: str,
    node_summary: str,
    history: str = "",
) -> str:
    """Build prompt for normal round."""
    system = f"""You are the {seat} seat in a multi-seat council deliberation.
Your role: {seat_profile.target_analogue}
Your lane: {seat_profile.lane}
Posture: {seat_profile.posture}
Challenge style: {seat_profile.challenge_style}
Resolution bias: {seat_profile.resolution_bias}

You must respond with JSON only. No markdown. No prose. JSON schema:
{{
  "seat": "{seat}",
  "node_id": "auto",
  "stance": "support|object|neutral|abstain",
  "summary": "one short explanation",
  "proposed_actions": [{{"action_type": "claim|alternative|refinement|support|object|evidence_needed", "title": "", "summary": ""}}],
  "vote": {{"position": "support|challenge|neutral|abstain", "reason": ""}},
  "confidence": 0.0-1.0
}}"""

    context = f"""Node: {node_title}
Summary: {node_summary}"""

    if history:
        context += f"\n\nHistory:\n{history[-500:]}"

    return f"{system}\n\n{context}\n\nRespond with JSON only."


def build_vote_prompt(
    seat: str,
    seat_profile: Any,
    node_title: str,
    node_summary: str,
) -> str:
    """Build prompt for vote round."""
    system = f"""You are the {seat} seat. Vote on this node.

Node: {node_title}
Summary: {node_summary}

Respond with JSON only. No markdown.
{{
  "seat": "{seat}",
  "node_id": "auto", 
  "vote": {{"position": "support|challenge|neutral|abstain", "reason": "short reason"}},
  "confidence": 0.0-1.0
}}"""
    return system


def build_contradiction_prompt(
    seat: str,
    seat_profile: Any,
    node_title: str,
    contradictions: List[str],
) -> str:
    """Build prompt for contradiction review."""
    system = f"""You are the {seat} seat. Review these contradictions.

Node: {node_title}
Contradictions: {chr(10).join(contradictions[-3:])}"""

    return f"""{system}

Respond with JSON only.
{{
  "seat": "{seat}",
  "stance": "support|object|neutral|abstain", 
  "summary": "how to resolve",
  "confidence": 0.0-1.0
}}"""


def build_escalation_prompt(
    seat: str,
    seat_profile: Any,
    node_title: str,
    gravity_stage: str,
) -> str:
    """Build prompt for escalation recommendation."""
    system = f"""You are the {seat} seat. Recommend next action.

Current gravity stage: {gravity_stage}
Node: {node_title}

Respond with JSON only.
{{
  "seat": "{seat}",
  "proposed_actions": [{{"action_type": "promote|demote|defer|split|discard", "title": "", "summary": ""}}],
  "confidence": 0.0-1.0
}}"""
    return system
