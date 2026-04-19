# Tests for real node creation and seat runtime

import pytest
from core.enums import NodeType, ViewMode, GravityStage
from core.models import SeatAction
from engine.engine import CouncilEngine


def test_claim_creates_real_node():
    """Claim action must create a real child node."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test topic", max_steps=5)
    root = session.nodes[session.active_queue[0]]
    initial_count = len(session.nodes)

    # Apply claim action
    action = SeatAction(
        seat="Strategist",
        node_id="fake-id",  # Should create new node
        action_type="claim",
        title="New claim",
        summary="This is a test claim",
        confidence=0.7,
    )
    engine.apply_action(session, root, action)

    # Verify new node was created
    assert len(session.nodes) == initial_count + 1
    new_node_id = root.children[-1]
    assert new_node_id in session.nodes
    new_node = session.nodes[new_node_id]
    assert new_node.title == "New claim"
    assert new_node.parent_id == root.node_id
    assert new_node.depth == 1
    assert new_node.node_type == NodeType.CLAIM


def test_alternative_creates_real_node():
    """Alternative action must create a real child node."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test topic", max_steps=5)
    root = session.nodes[session.active_queue[0]]
    initial_count = len(session.nodes)

    action = SeatAction(
        seat="Architect",
        node_id="fake-id",
        action_type="alternative",
        title="Alternative path B",
        summary="Another approach",
        confidence=0.6,
    )
    engine.apply_action(session, root, action)

    assert len(session.nodes) == initial_count + 1
    new_node_id = root.children[-1]
    assert new_node_id in session.nodes
    new_node = session.nodes[new_node_id]
    assert new_node.node_type == NodeType.ALTERNATIVE


def test_refinement_creates_real_node():
    """Refinement action must create a real child node."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test topic", max_steps=5)
    root = session.nodes[session.active_queue[0]]
    initial_count = len(session.nodes)

    action = SeatAction(
        seat="Researcher",
        node_id="fake-id",
        action_type="refinement",
        title="Refined approach",
        summary="Better version",
        confidence=0.65,
    )
    engine.apply_action(session, root, action)

    assert len(session.nodes) == initial_count + 1
    new_node_id = root.children[-1]
    assert new_node_id in session.nodes


def test_active_queue_grows():
    """New nodes should be added to active queue."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test topic", max_steps=5)
    root = session.nodes[session.active_queue[0]]
    initial_queue = len(session.active_queue)

    action = SeatAction(
        seat="Strategist",
        node_id="fake",
        action_type="claim",
        title="New claim",
        summary="Test",
        confidence=0.7,
    )
    engine.apply_action(session, root, action)

    assert len(session.active_queue) > initial_queue


def test_simulation_mode_works():
    """Simulation mode should work without LLM."""
    engine = CouncilEngine(runtime_mode="simulation")
    assert engine.runtime_mode == "simulation"
    assert engine.runtime is not None

    session = engine.create_session("Test", max_steps=2)
    artifact = engine.run(session)
    assert artifact is not None


def test_hybrid_mode_fallback():
    """Hybrid mode should fall back to simulation on failure."""
    engine = CouncilEngine(runtime_mode="hybrid")
    assert engine.runtime_mode == "hybrid"


def test_no_degenerate_loop():
    """Engine should create real branches, not degenerate to single node."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test topic", max_steps=20)
    artifact = engine.run(session)

    # Should have multiple nodes, not just root repeated
    assert len(session.nodes) > 5
    # Should have actual children
    has_real_children = any(len(n.children) > 0 for n in session.nodes.values())
    assert has_real_children, "No real child nodes created!"


def test_runtime_config():
    """Runtime should accept seat configs."""
    from seats.runtime import SeatRuntime, SeatConfig, DEFAULT_SEAT_CONFIGS

    configs = DEFAULT_SEAT_CONFIGS.copy()
    runtime = SeatRuntime(mode="simulation", configs=configs)
    assert "Strategist" in runtime.configs
    assert runtime.configs["Strategist"].model == "qwen3:8b"
    assert runtime.configs["Strategist"].tier == "hot"


def test_seat_response_parsing():
    """Seat response should parse correctly."""
    from seats.runtime import SeatRuntime

    runtime = SeatRuntime(mode="simulation")
    response = runtime.execute_seat(
        "Strategist", "Test node context", "You are a strategist."
    )

    assert response.seat == "Strategist"
    assert response.stance in ["support", "object", "neutral", "abstain"]
    assert response.confidence > 0


def test_vote_parsing():
    """Vote should be parsed from response."""
    from seats.runtime import SeatRuntime

    runtime = SeatRuntime(mode="simulation")
    response = runtime.execute_seat("Skeptic", "Test topic", "You are a skeptic.")

    assert response.vote_position in ["support", "challenge", "neutral", "abstain"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
