from enum import Enum


class NodeType(str, Enum):
    # Main deliberation flow
    TOPIC = "topic"
    CLAIM = "claim"
    OBJECTION = "objection"
    ALTERNATIVE = "alternative"
    REFINEMENT = "refinement"
    EVIDENCE_NEEDED = "evidence_needed"
    RESOLUTION = "resolution"
    # Creative flow (idea mode)
    IDEA_SEED = "idea_seed"
    TWIST = "twist"
    MASHUP = "mashup"
    SCENARIO = "scenario"
    EXPERIMENT = "experiment"
    SALVAGE = "salvage"
    SPECULATIVE_RESOLUTION = "speculative_resolution"


class NodeStatus(str, Enum):
    ACTIVE = "active"
    CONTESTED = "contested"
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    DEAD = "dead"
    BLOCKED = "blocked"


class ResolutionState(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MERGED = "merged"
    UNRESOLVED = "unresolved"
    DEFERRED = "deferred"
    EVIDENCE_NEEDED = "evidence_needed"


class SeatHealth(str, Enum):
    ACTIVE = "active"
    SUPPORT = "support"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    KILLED = "killed"


class ActionType(str, Enum):
    CLAIM = "claim"
    SUPPORT = "support"
    OBJECT = "object"
    ALTERNATIVE = "alternative"
    REFINEMENT = "refinement"
    EVIDENCE_NEEDED = "evidence_needed"
    RESOLUTION = "resolution"
    ABSTAIN = "abstain"


class FinalPosture(str, Enum):
    STAND = "stand"
    REVISE = "revise"
    ABSTAIN = "abstain"
    UNRESOLVED = "unresolved"


class ViewMode(str, Enum):
    COUNCIL = "council"
    DUEL = "duel"
    CHALLENGE = "challenge"
    STRESS = "stress"
    IDEA = "idea"
    OPEN = "open"


class GravityStage(str, Enum):
    EXPLORATORY = "exploratory"
    ADVISORY = "advisory"
    FORMAL = "formal"
    TRIBUNAL = "tribunal"


class IdeaPhase(str, Enum):
    SEED = "seed"
    MUTATE = "mutate"
    MASHUP = "mashup"
    SALVAGE = "salvage"
    PRESSURE = "pressure"
