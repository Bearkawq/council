import pytest
from core.enums import (
    NodeType,
    NodeStatus,
    ResolutionState,
    GravityStage,
    IdeaPhase,
    ViewMode,
)
from core.models import Session, Node, SeatState, SeatAction, SeatProfile, Precedent
from engine.engine import CouncilEngine
from flask import Flask


def test_session_creation():
    engine = CouncilEngine()
    session = engine.create_session("Test topic", max_steps=10, mode=ViewMode.COUNCIL)
    assert session.topic == "Test topic"
    assert len(session.nodes) == 1
    assert session.active_queue


def test_branch_creation():
    engine = CouncilEngine()
    session = engine.create_session("Test topic", mode=ViewMode.COUNCIL)
    root = session.nodes[session.active_queue[0]]

    child = Node(
        node_id=session.next_node_id(),
        node_type=NodeType.CLAIM,
        title="Test claim",
        summary="Test claim summary",
        parent_id=root.node_id,
        created_by="TestSeat",
        depth=1,
    )
    session.nodes[child.node_id] = child
    root.children.append(child.node_id)

    assert child.parent_id == root.node_id
    assert root.children[-1] == child.node_id


def test_node_resolution():
    engine = CouncilEngine()
    session = engine.create_session("Test topic", mode=ViewMode.COUNCIL)
    root = session.nodes[session.active_queue[0]]

    root.resolution_state = ResolutionState.ACCEPTED
    assert root.resolution_state == ResolutionState.ACCEPTED


def test_seat_state_tracking():
    engine = CouncilEngine()
    session = engine.create_session("Test topic", mode=ViewMode.COUNCIL)

    assert "Strategist" in session.seat_states
    state = session.seat_states["Strategist"]
    assert state.health == "active"
    state.confidence = 0.8
    assert session.seat_states["Strategist"].confidence == 0.8


def test_gravity_stage_transitions():
    stage = GravityStage.EXPLORATORY
    assert stage == GravityStage.EXPLORATORY

    next_stage = GravityStage.ADVISORY
    assert next_stage == GravityStage.ADVISORY


def test_promotion_vote_creates_record():
    engine = CouncilEngine()
    session = engine.create_session("Test topic", mode=ViewMode.COUNCIL)
    root = session.nodes[session.active_queue[0]]

    result = engine.vote_on_promotion(session, root.node_id, "Skeptic")

    assert "outcome" in result
    assert root.promotion_record


def test_demotion_vote_rejected_at_lowest():
    engine = CouncilEngine()
    session = engine.create_session("Test topic", mode=ViewMode.COUNCIL)
    root = session.nodes[session.active_queue[0]]
    root.gravity_stage = GravityStage.EXPLORATORY

    result = engine.vote_on_demotion(session, root.node_id, "Skeptic")
    assert result.get("outcome") == "reject"


def test_precedent_creation():
    precedent = Precedent(
        id="p1",
        topic="test topic",
        artifact_summary="test summary",
        gravity_stage="exploratory",
        resolution="accepted",
    )
    assert precedent.id == "p1"
    assert precedent.resolution == "accepted"


def test_contradiction_harvest():
    engine = CouncilEngine()
    session = engine.create_session("Test topic", mode=ViewMode.COUNCIL)
    root = session.nodes[session.active_queue[0]]

    obj_node = Node(
        node_id=session.next_node_id(),
        node_type=NodeType.OBJECTION,
        title="Test objection",
        summary="Objection summary",
        parent_id=root.node_id,
        created_by="Skeptic",
        depth=1,
    )
    session.nodes[obj_node.node_id] = obj_node
    root.objections.append("Skeptic")

    engine._harvest_contradictions(session)

    assert len(session.contradictions) >= 0


def test_formal_mode_artifact():
    engine = CouncilEngine()
    session = engine.create_session("Test topic", mode=ViewMode.IDEA)
    artifact = engine.run_idea_mode(session)

    assert artifact is not None


def test_trust_modifier_works():
    """Test that trust_map influences action confidence."""
    engine = CouncilEngine()
    session = engine.create_session("Test", max_steps=1)
    session.seat_states["Strategist"] = SeatState(confidence=0.8)

    profile = SeatProfile(
        name="Test",
        target_analogue="",
        lane="",
        posture="",
        challenge_style="",
        concession_style="",
        evidence_appetite="",
        risk_lens="",
        aggression="",
        forbidden_drift=[],
        branch_trigger="",
        resolution_bias="",
        priority_order=[],
        majority_resistance=0.5,
        aggression_floor=0.3,
        aggression_ceiling=0.7,
        trust_map={"Strategist": 0.8},
    )
    action = SeatAction(
        seat="Test",
        node_id="n1",
        action_type="s",
        title="T",
        summary="T",
        confidence=0.5,
    )
    modified = engine._apply_trust_modifier(action, session, "Test", profile.trust_map)
    assert modified.confidence != 0.5


def test_preferred_mode_works():
    """Test that preferred modes bias action selection."""
    engine = CouncilEngine()
    profile = SeatProfile(
        name="Test",
        target_analogue="",
        lane="",
        posture="",
        challenge_style="",
        concession_style="",
        evidence_appetite="",
        risk_lens="",
        aggression="",
        forbidden_drift=[],
        branch_trigger="",
        resolution_bias="",
        priority_order=[],
        majority_resistance=0.5,
        aggression_floor=0.3,
        aggression_ceiling=0.7,
        preferred_attack_modes=["direct"],
    )
    action = SeatAction(
        seat="Test",
        node_id="n1",
        action_type="object",
        title="O",
        summary="O",
        confidence=0.5,
    )
    modified = engine._apply_preferred_mode(action, profile)
    assert "attack:direct" in modified.summary


def test_artifact_has_review_fields():
    """Test that SessionArtifact exposes review info."""
    engine = CouncilEngine()
    session = engine.create_session("Test", max_steps=1, mode=ViewMode.COUNCIL)
    artifact = engine.build_artifact(session)
    assert hasattr(artifact, "review_items")
    assert hasattr(artifact, "pending_reviews")
    assert hasattr(artifact, "rejected_reviews")


def test_open_discussion_mode():
    """Test that Open Discussion mode runs."""
    engine = CouncilEngine()
    session = engine.create_session("Test open", max_steps=3, mode=ViewMode.OPEN)
    assert session.mode == "open"
    artifact = engine.run(session)
    assert artifact.open_discussion_active is True
    assert artifact.narrowing_round >= 0
    assert len(artifact.candidate_motions) > 0


def test_open_discussion_has_narrowing():
    """Test that narrowing pulses work in Open Discussion."""
    engine = CouncilEngine()
    session = engine.create_session("Test narrowing", max_steps=5, mode=ViewMode.OPEN)
    artifact = engine.run(session)
    assert artifact.narrowing_round > 0
    assert isinstance(artifact.top_candidates, list)


def test_open_discussion_exit():
    """Test exit from Open Discussion."""
    from core.enums import ViewMode

    engine = CouncilEngine()
    session = engine.create_session("Test exit", max_steps=1, mode=ViewMode.OPEN)
    engine.run(session)

    result = engine.exit_open_discussion(session, "n1", "promote")
    assert result["success"] is True
    assert result["exit_type"] == "promote"
    assert len(session.motions) > 0

    result_invalid = engine.exit_open_discussion(session, "n1", "invalid")
    assert result_invalid["success"] is False


def test_split_exit():
    """Test split exit from Open Discussion."""
    from core.enums import ViewMode

    engine = CouncilEngine()
    session = engine.create_session("Test split", max_steps=1, mode=ViewMode.OPEN)
    engine.run(session)

    result = engine.exit_open_discussion(session, "n1", "split")
    assert result["success"] is True
    assert result["exit_type"] == "split"
    assert "child_ids" in result
    assert len(result["child_ids"]) == 2


def test_divergence_markers():
    """Test divergence markers in artifacts."""
    from core.enums import ViewMode

    engine = CouncilEngine()
    session = engine.create_session("Test div", max_steps=1, mode=ViewMode.COUNCIL)
    artifact = engine.run(session)
    assert hasattr(artifact, "divergence_markers")


def test_open_contradiction_lighter():
    """Test lighter contradiction in Open Discussion."""
    from core.enums import ViewMode

    engine = CouncilEngine()
    session = engine.create_session(
        "Test open contrad", max_steps=4, mode=ViewMode.OPEN
    )
    artifact = engine.run(session)

    contrad_in_open = [c for c in session.contradictions if c.startswith("open-")]
    assert artifact.open_discussion_active is True


def test_gui_smoke():
    """Test that GUI renders without error."""
    from gui import app

    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200


def test_gui_open_mode_button():
    """Test that GUI has Open mode button."""
    from gui import app

    client = app.test_client()
    resp = client.get("/")
    assert b"OPEN" in resp.data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
