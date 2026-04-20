from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from core.enums import NodeType, NodeStatus, ResolutionState, FinalPosture, GravityStage


@dataclass
class CandidateMotion:
    """A candidate line/motion before formal proposal."""

    node_id: str
    title: str
    proposer: str
    rank: int = 0
    status: str = "exploratory"  # exploratory, narrowing, promoted, discarded
    support_count: int = 0
    objection_count: int = 0
    unresolved_question: str = ""


@dataclass
class OpenDiscussionState:
    """State tracking for Open Discussion mode."""

    candidate_lines: List[CandidateMotion] = field(default_factory=list)
    narrowing_round: int = 0
    unresolved_questions: List[str] = field(default_factory=list)
    diverged_from: Optional[str] = None
    top_candidates: List[str] = field(default_factory=list)


@dataclass
class Motion:
    """Motion to advance a branch through deliberation stages."""

    node_id: str
    motion_type: str
    proposer: str
    stage: str
    votes: Dict[str, str] = field(default_factory=dict)
    outcome: str = "pending"
    round: int = 0


@dataclass
class ReviewItem:
    """Review/promotion review item for a branch."""

    node_id: str
    review_type: str
    proposer: str
    stage: str
    outcome: str = "pending"
    forced: bool = False
    minority_opposed: List[str] = field(default_factory=list)
    citations: int = 0


@dataclass
class RoundRecord:
    """Round-level record for chamber state."""

    round: int
    active_nodes: List[str]
    completed_actions: List[str] = field(default_factory=list)
    contradictions_raised: List[str] = field(default_factory=list)
    motions_proposed: List[str] = field(default_factory=list)
    reviews_proposed: List[str] = field(default_factory=list)
    chamber_summary: str = ""
    navigator_state: Optional[Dict[str, Any]] = None


@dataclass
class ContradictionEntry:
    """Structured contradiction tracking."""

    id: str
    source_seat: str
    target_node_id: str
    summary: str
    status: str = "open"  # open, narrowed, merged, resolved
    risk_if_ignored: List[str] = field(default_factory=list)
    created_at: int = 0


@dataclass
class Precedent:
    """Explicit, challengeable precedent from past branches."""

    id: str
    topic: str
    artifact_summary: str
    gravity_stage: str
    resolution: str
    citation_count: int = 0
    challenged: bool = False
    challenge_outcome: str = ""


@dataclass
class SeatProfile:
    name: str
    target_analogue: str
    lane: str
    posture: str
    challenge_style: str
    concession_style: str
    evidence_appetite: str
    risk_lens: str
    aggression: str
    forbidden_drift: List[str]
    branch_trigger: str
    resolution_bias: str
    priority_order: List[str]
    majority_resistance: float
    aggression_floor: float
    aggression_ceiling: float
    signature_values: Dict[str, float] = field(default_factory=lambda: {})
    preferred_attack_modes: List[str] = field(default_factory=list)
    preferred_refinement_modes: List[str] = field(default_factory=list)
    trust_map: Dict[str, float] = field(default_factory=dict)
    identity_strength: float = 0.5
    identity_drift_resistance: float = 0.5
    memory_weight: float = 0.3
    frustration: float = 0.0
    momentum: float = 0.0


@dataclass
class SeatState:
    health: str = "active"
    confidence: float = 0.65
    concessions: int = 0
    objections_made: int = 0
    supports_made: int = 0
    revisions: int = 0
    unresolved_count: int = 0
    contradiction_hits: List[str] = field(default_factory=list)
    interaction_memory: List[str] = field(default_factory=list)
    lane_drift_flags: int = 0
    repeated_points: int = 0
    last_posture: Optional[str] = None
    direct_challenges: int = 0
    minority_preserved: int = 0
    self_assertion: float = 0.5
    emotional_temperature: float = 0.5
    stubbornness: float = 0.5
    adaptability: float = 0.5
    frustration: float = 0.0
    momentum: float = 0.0
    last_interaction_round: int = 0


@dataclass
class Node:
    node_id: str
    node_type: NodeType
    title: str
    summary: str
    parent_id: Optional[str]
    created_by: str
    depth: int
    status: NodeStatus = NodeStatus.ACTIVE
    resolution_state: Optional[ResolutionState] = None
    linked_seats: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    supports: List[str] = field(default_factory=list)
    objections: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    refinements: List[str] = field(default_factory=list)
    evidence_requests: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    stance_map: Dict[str, str] = field(default_factory=dict)
    confidence_map: Dict[str, float] = field(default_factory=dict)
    what_changes_mind: Dict[str, str] = field(default_factory=dict)
    contradictions: List[str] = field(default_factory=list)
    gravity: float = 0.5
    support_level: float = 0.0
    risk_if_ignored: List[str] = field(default_factory=list)
    final_postures: Dict[str, FinalPosture] = field(default_factory=dict)
    gravity_stage: GravityStage = GravityStage.EXPLORATORY
    promoted: bool = False
    promotion_votes: List[str] = field(default_factory=list)


@dataclass
class SeatAction:
    seat: str
    node_id: str
    action_type: str
    title: str
    summary: str
    confidence: float
    target_node_id: Optional[str] = None
    final_posture: Optional[FinalPosture] = None
    resolution_state: Optional[ResolutionState] = None
    what_would_change_mind: Optional[str] = None
    stance: Optional[str] = None
    concession_of: Optional[str] = None
    challenge_target: Optional[str] = None
    confidence_delta: Optional[float] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class RuntimeMetadata:
    seat: str
    node_id: str
    runtime_mode: str
    model_used: str
    fallback_used: bool = False
    fallback_reason: str = ""
    failure_class: str = ""
    failure_reason: str = ""
    parse_status: str = "success"
    latency_ms: int = 0
    action_count: int = 0
    actions_filtered: int = 0
    summary: str = ""
    error:Optional[str] = None
    proposed_actions: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ReplayEvent:
    step: int
    event_type: str
    detail: str
    seat: Optional[str] = None
    node_id: Optional[str] = None


@dataclass
class SessionArtifact:
    root_resolution: Optional[ResolutionState] = None
    consensus_points: List[str] = field(default_factory=list)
    minority_objections: List[str] = field(default_factory=list)
    unresolved_branches: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    keep: List[str] = field(default_factory=list)
    remove: List[str] = field(default_factory=list)
    upgrade: List[str] = field(default_factory=list)
    branch_scores: Dict[str, float] = field(default_factory=dict)
    replay_event_count: int = 0
    seat_drift: Dict[str, int] = field(default_factory=dict)
    final_postures: Dict[str, str] = field(default_factory=dict)
    mode: str = "council"
    gravity_stage_counts: Dict[str, int] = field(default_factory=dict)
    promotions: List[str] = field(default_factory=list)
    rejected_promotions: List[str] = field(default_factory=list)
    review_items: List[str] = field(default_factory=list)
    pending_reviews: List[str] = field(default_factory=list)
    rejected_reviews: List[str] = field(default_factory=list)
    open_discussion_active: bool = False
    candidate_motions: List[str] = field(default_factory=list)
    top_candidates: List[str] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    narrowing_round: int = 0
    divergence_markers: List[str] = field(default_factory=list)


@dataclass
class IdeaArtifact:
    best_raw_ideas: List[str] = field(default_factory=list)
    best_mashups: List[str] = field(default_factory=list)
    best_salvage: List[str] = field(default_factory=list)
    best_experiments: List[str] = field(default_factory=list)
    phase: str = ""


@dataclass
class SimulationParams:
    identity_weight: float = 0.3
    social_weight: float = 0.25
    fatigue_weight: float = 0.15
    contradiction_weight: float = 0.2
    review_weight: float = 0.1
    precedent_weight: float = 0.1
    confidence_decay: float = 0.02
    fatigue_rate: float = 0.05
    frustration_threshold: float = 0.75
    trust_decay: float = 0.01
    drift_resistance_boost: float = 0.1
    min_rounds_for_recovery: int = 3
    max_interaction_memory: int = 20
    contradiction_hits_threshold: int = 3
    max_proposed_actions_per_seat: int = 3

    def validate(self) -> List[str]:
        errors = []
        if not 0.0 <= self.identity_weight <= 1.0:
            errors.append(f"identity_weight must be 0-1, got {self.identity_weight}")
        if not 0.0 <= self.social_weight <= 1.0:
            errors.append(f"social_weight must be 0-1, got {self.social_weight}")
        if not 0.0 <= self.fatigue_weight <= 1.0:
            errors.append(f"fatigue_weight must be 0-1, got {self.fatigue_weight}")
        if not 0.0 <= self.contradiction_weight <= 1.0:
            errors.append(
                f"contradiction_weight must be 0-1, got {self.contradiction_weight}"
            )
        if not 0.0 <= self.confidence_decay <= 0.5:
            errors.append(
                f"confidence_decay must be 0-0.5, got {self.confidence_decay}"
            )
        if not 0.0 <= self.fatigue_rate <= 0.5:
            errors.append(f"fatigue_rate must be 0-0.5, got {self.fatigue_rate}")
        if not 0.0 <= self.frustration_threshold <= 1.0:
            errors.append(
                f"frustration_threshold must be 0-1, got {self.frustration_threshold}"
            )
        if self.min_rounds_for_recovery < 1:
            errors.append(
                f"min_rounds_for_recovery must be >=1, got {self.min_rounds_for_recovery}"
            )
        if self.max_interaction_memory < 1:
            errors.append(
                f"max_interaction_memory must be >=1, got {self.max_interaction_memory}"
            )
        if self.contradiction_hits_threshold < 1:
            errors.append(
                f"contradiction_hits_threshold must be >=1, got {self.contradiction_hits_threshold}"
            )
        total = (
            self.identity_weight
            + self.social_weight
            + self.fatigue_weight
            + self.contradiction_weight
        )
        if total > 1.0:
            errors.append(f"weight sum ({total}) exceeds 1.0")
        return errors


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def validate_seat_state(state: SeatState) -> List[str]:
    errors = []
    if state.confidence < 0.0 or state.confidence > 1.0:
        errors.append(f"confidence must be 0-1, got {state.confidence}")
    if state.self_assertion < 0.0 or state.self_assertion > 1.0:
        errors.append(f"self_assertion must be 0-1, got {state.self_assertion}")
    if state.emotional_temperature < 0.0 or state.emotional_temperature > 1.0:
        errors.append(
            f"emotional_temperature must be 0-1, got {state.emotional_temperature}"
        )
    if state.stubbornness < 0.0 or state.stubbornness > 1.0:
        errors.append(f"stubbornness must be 0-1, got {state.stubbornness}")
    if state.adaptability < 0.0 or state.adaptability > 1.0:
        errors.append(f"adaptability must be 0-1, got {state.adaptability}")
    if state.frustration < 0.0 or state.frustration > 1.0:
        errors.append(f"frustration must be 0-1, got {state.frustration}")
    if state.momentum < 0.0 or state.momentum > 1.0:
        errors.append(f"momentum must be 0-1, got {state.momentum}")
    return errors


def sanitize_seat_state(state: SeatState) -> SeatState:
    state.confidence = clamp(state.confidence)
    state.self_assertion = clamp(state.self_assertion)
    state.emotional_temperature = clamp(state.emotional_temperature)
    state.stubbornness = clamp(state.stubbornness)
    state.adaptability = clamp(state.adaptability)
    state.frustration = clamp(state.frustration)
    state.momentum = clamp(state.momentum)
    state.health = state.health or "active"
    if state.health not in (
        "active",
        "support",
        "degraded",
        "blocked",
        "suspended",
        "killed",
    ):
        state.health = "active"
    return state


def validate_motion_stage_transition(from_stage: str, to_stage: str) -> bool:
    valid_transitions = {
        "exploratory": ["advisory", "formal"],
        "advisory": ["formal", "tribunal"],
        "formal": ["tribunal"],
        "tribunal": [],
    }
    return to_stage in valid_transitions.get(from_stage, [])


@dataclass
class Session:
    topic: str
    mode: str = "council"
    max_steps: int = 50
    max_depth: int = 6
    contradiction_pressure_enabled: bool = True
    step_count: int = 0
    node_counter: int = 1
    nodes: Dict[str, Node] = field(default_factory=dict)
    active_queue: List[str] = field(default_factory=list)
    replay: List[ReplayEvent] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    contradiction_ledger: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    seat_states: Dict[str, SeatState] = field(default_factory=dict)
    last_outputs: Dict[str, str] = field(default_factory=dict)
    seen_action_hashes: set = field(default_factory=set)
    template_tags: set = field(default_factory=set)
    idea_phase: Optional[str] = None
    idea_artifacts: IdeaArtifact = field(default_factory=lambda: IdeaArtifact())
    formal_session: bool = False
    opening_statements: List[str] = field(default_factory=list)
    challenge_round_findings: List[str] = field(default_factory=list)
    minority_reports: Dict[str, str] = field(default_factory=dict)
    risk_if_ignored: List[str] = field(default_factory=list)
    precedent_history: List[Precedent] = field(default_factory=list)
    motions: List[Motion] = field(default_factory=list)
    reviews: List[ReviewItem] = field(default_factory=list)
    round_history: List[RoundRecord] = field(default_factory=list)
    open_discussion: Optional[OpenDiscussionState] = None
    runtime_metadata: List[RuntimeMetadata] = field(default_factory=list)

    def next_node_id(self) -> str:
        nid = f"n{self.node_counter}"
        self.node_counter += 1
        return nid

    def add_event(
        self,
        event_type: str,
        detail: str,
        seat: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> None:
        self.replay.append(
            ReplayEvent(
                step=len(self.replay) + 1,
                event_type=event_type,
                detail=detail,
                seat=seat,
                node_id=node_id,
            )
        )
