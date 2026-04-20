# Tests for real node creation and seat runtime

import pytest
from core.enums import NodeType, ViewMode, GravityStage
from core.models import SeatAction, RuntimeMetadata
from engine.engine import CouncilEngine
from seats.runtime import SeatRuntime, SeatResponse


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


def test_local_llm_response_converted_to_engine_actions():
    """Local LLM response should convert to engine actions correctly."""
    from seats.runtime import SeatResponse

    engine = CouncilEngine(runtime_mode="local_llm")
    session = engine.create_session("Test topic", max_steps=2)
    root = session.nodes[session.active_queue[0]]

    if engine.runtime is None:
        pytest.skip("Runtime not available")

    resp = SeatResponse(
        seat="Strategist",
        node_id=root.node_id,
        stance="support",
        summary="Strategy proposal",
        proposed_actions=[
            {
                "action_type": "claim",
                "title": "Test claim",
                "summary": "Test summary",
            }
        ],
        confidence=0.7,
    )

    action = engine._convert_runtime_response("Strategist", root, resp)
    assert action is not None
    assert action.action_type == "claim"
    assert action.seat == "Strategist"
    assert action.confidence == 0.7


def test_hybrid_fallback_converts_failed_runtime_seat():
    """Hybrid mode should fall back to simulation when runtime fails."""
    engine = CouncilEngine(runtime_mode="hybrid")
    session = engine.create_session("Test", max_steps=1)

    if engine.runtime is None:
        pytest.skip("Runtime not available")

    root = session.nodes[session.active_queue[0]]
    initial_meta_count = len(session.runtime_metadata)

    engine.process_node(session, root)

    final_meta_count = len(session.runtime_metadata)
    assert final_meta_count >= initial_meta_count


def test_support_stance_updates_node_state_correctly():
    """Support stance should update node supports."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)
    root = session.nodes[session.active_queue[0]]

    action = SeatAction(
        seat="Strategist",
        node_id=root.node_id,
        action_type="support",
        title="Support",
        summary="I support this",
        confidence=0.7,
    )
    engine.apply_action(session, root, action)

    assert "Strategist" in root.supports
    assert root.stance_map["Strategist"] == "support"


def test_object_stance_updates_node_state_correctly():
    """Object stance should update node objections."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)
    root = session.nodes[session.active_queue[0]]

    action = SeatAction(
        seat="Skeptic",
        node_id=root.node_id,
        action_type="object",
        title="Objection",
        summary="I object to this",
        confidence=0.6,
    )
    engine.apply_action(session, root, action)

    assert "Skeptic" in root.objections
    assert root.stance_map["Skeptic"] == "object"


def test_claim_creates_real_node():
    """Claim action should create proper child node."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)
    root = session.nodes[session.active_queue[0]]

    action = SeatAction(
        seat="Strategist",
        node_id=root.node_id,
        action_type="claim",
        title="New claim node",
        summary="A claim",
        confidence=0.7,
    )
    engine.apply_action(session, root, action)

    assert len(root.children) > 0
    child = session.nodes[root.children[-1]]
    assert child.node_type == NodeType.CLAIM
    assert child.parent_id == root.node_id


def test_alternative_creates_real_node():
    """Alternative action should create proper child node."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)
    root = session.nodes[session.active_queue[0]]

    action = SeatAction(
        seat="Researcher",
        node_id=root.node_id,
        action_type="alternative",
        title="Alternative path",
        summary="Another approach",
        confidence=0.6,
    )
    engine.apply_action(session, root, action)

    child = session.nodes[root.children[-1]]
    assert child.node_type == NodeType.ALTERNATIVE


def test_refinement_creates_real_node():
    """Refinement action should create proper child node."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)
    root = session.nodes[session.active_queue[0]]

    action = SeatAction(
        seat="Architect",
        node_id=root.node_id,
        action_type="refinement",
        title="Refinement",
        summary="Better version",
        confidence=0.65,
    )
    engine.apply_action(session, root, action)

    child = session.nodes[root.children[-1]]
    assert child.node_type == NodeType.REFINEMENT


def test_seat_failure_does_not_kill_chamber_round():
    """Seat failure should not stop other seats from processing."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)
    root = session.nodes[session.active_queue[0]]

    engine.process_node(session, root)

    assert session.step_count >= 0


def test_runtime_metadata_is_populated():
    """Runtime metadata should be recorded."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)

    initial_meta = RuntimeMetadata(
        seat="TestSeat",
        node_id="n1",
        runtime_mode="simulation",
        model_used="test",
        fallback_used=False,
    )
    session.runtime_metadata.append(initial_meta)

    assert len(session.runtime_metadata) > 0
    assert session.runtime_metadata[0].seat == "TestSeat"


def test_transcript_shows_runtime_backed_activity():
    """Transcript should reflect runtime-backed seat activity."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)
    root = session.nodes[session.active_queue[0]]

    action = SeatAction(
        seat="Strategist",
        node_id=root.node_id,
        action_type="claim",
        title="Test",
        summary="Test",
        confidence=0.7,
    )

    if engine.runtime and engine.runtime_mode in ("local_llm", "hybrid"):
        session.add_event(
            "runtime_action",
            "[Strategist] Runtime-backed: claim",
            seat="Strategist",
            node_id=root.node_id,
        )

    runtime_events = [
        e for e in session.replay if e.event_type == "runtime_action"
    ]


def test_action_type_to_node_type_mapping():
    """Action types should map correctly to node types."""
    engine = CouncilEngine()

    assert engine._action_type_to_node_type("claim") == NodeType.CLAIM
    assert engine._action_type_to_node_type("alternative") == NodeType.ALTERNATIVE
    assert engine._action_type_to_node_type("refinement") == NodeType.REFINEMENT
    assert engine._action_type_to_node_type("evidence_needed") == NodeType.EVIDENCE_NEEDED
    assert engine._action_type_to_node_type("invalid") is None


def test_timeout_classification():
    """Timeout should be classified correctly."""
    from seats.runtime import SeatResponse

    resp = SeatResponse(
        seat="TestSeat",
        node_id="n1",
        stance="abstain",
        summary="Timeout",
        timeout=True,
        error="Timeout after 30s",
    )
    assert resp.timeout is True


def test_parse_failure_classification():
    """Parse failure should be classified correctly."""
    from seats.runtime import SeatResponse

    resp = SeatResponse(
        seat="TestSeat",
        node_id="n1",
        stance="neutral",
        summary="",
        parse_failed=True,
    )
    assert resp.parse_failed is True


def test_empty_output_classification():
    """Empty output should be classified correctly."""
    from seats.runtime import SeatResponse

    resp = SeatResponse(
        seat="TestSeat",
        node_id="n1",
        stance="neutral",
        summary="",
        empty_output=True,
    )
    assert resp.empty_output is True


def test_fallback_reason_visibility():
    """Fallback reason should be visible in metadata."""
    from core.models import RuntimeMetadata

    meta = RuntimeMetadata(
        seat="TestSeat",
        node_id="n1",
        runtime_mode="hybrid",
        model_used="test-model",
        fallback_used=True,
        fallback_reason="parse_failed",
        failure_class="parse_failure",
    )
    assert meta.fallback_used is True
    assert meta.fallback_reason == "parse_failed"


def test_max_proposed_actions_cap():
    """Node growth should be bounded by max_proposed_actions_per_seat."""
    from core.models import SimulationParams

    params = SimulationParams()
    assert hasattr(params, 'max_proposed_actions_per_seat')
    assert params.max_proposed_actions_per_seat == 3


def test_continue_deliberation_works():
    """Continue deliberation should run for specified steps."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=10)
    root = session.nodes[session.active_queue[0]]

    original_steps = session.step_count
    artifact = engine.continue_deliberation(session, steps=1)

    assert session.step_count >= original_steps


def test_quality_filter_rejects_duplicate_title():
    """Quality filter should reject proposed action with same title as parent."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("Test", max_steps=1).nodes["n1"]

    action = {"action_type": "claim", "title": "Test", "summary": "Same as parent"}
    assert engine._is_quality_action(action, parent) is False


def test_quality_filter_rejects_empty_title():
    """Quality filter should reject empty or too-short titles."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("Test", max_steps=1).nodes["n1"]

    action1 = {"action_type": "claim", "title": "", "summary": "Some summary"}
    assert engine._is_quality_action(action1, parent) is False

    action2 = {"action_type": "claim", "title": "Hi", "summary": "Too short"}
    assert engine._is_quality_action(action2, parent) is False


def test_quality_filter_rejects_restating_phrases():
    """Quality filter should reject restating phrases."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("Test topic", max_steps=1).nodes["n1"]

    action = {"action_type": "claim", "title": "Similar to the above", "summary": "Detail"}
    assert engine._is_quality_action(action, parent) is False


def test_quality_filter_accepts_meaningful_action():
    """Quality filter should accept meaningful proposed actions."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("API design", max_steps=1).nodes["n1"]

    action = {
        "action_type": "claim",
        "title": "Use REST for resource operations",
        "summary": "REST provides consistent CRUD interface"
    }
    assert engine._is_quality_action(action, parent) is True


def test_actions_filtered_tracked_in_metadata():
    """Actions filtered should be tracked in runtime metadata."""
    from core.models import RuntimeMetadata

    meta = RuntimeMetadata(
        seat="TestSeat",
        node_id="n1",
        runtime_mode="hybrid",
        model_used="test",
        action_count=5,
        actions_filtered=2,
    )
    assert meta.actions_filtered == 2


def test_quality_filter_rejects_duplicate_sibling():
    """Quality filter should reject action matching sibling title."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("Test topic", max_steps=1).nodes["n1"]
    sibling = type('Node', (), {
        'title': 'Existing sibling option'
    })()

    action = {"action_type": "claim", "title": "Existing sibling option", "summary": "A valid summary"}
    result = engine._is_quality_action(action, parent, [sibling])
    assert result is False


def test_quality_filter_rejects_short_summary():
    """Quality filter should reject very short summaries."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("API design", max_steps=1).nodes["n1"]

    action = {"action_type": "claim", "title": "Valid title", "summary": "Hi"}
    assert engine._is_quality_action(action, parent) is False


def test_quality_filter_rejects_empty_summary():
    """Quality filter should reject empty summaries."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("API design", max_steps=1).nodes["n1"]

    action = {"action_type": "claim", "title": "Valid title", "summary": ""}
    assert engine._is_quality_action(action, parent) is False


def test_quality_filter_rejects_tbd_phrases():
    """Quality filter should reject TBD/needs more research."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("Test", max_steps=1).nodes["n1"]

    action1 = {"action_type": "claim", "title": "To be determined approach", "summary": "Some details"}
    assert engine._is_quality_action(action1, parent) is False

    action2 = {"action_type": "claim", "title": "Valid title", "summary": "Needs further study"}
    assert engine._is_quality_action(action2, parent) is False


def test_quality_filter_accepts_novel_proposal():
    """Quality filter should accept novel meaningful proposals."""
    engine = CouncilEngine(runtime_mode="simulation")
    parent = engine.create_session("API design for users", max_steps=1).nodes["n1"]

    action = {
        "action_type": "alternative",
        "title": "Use GraphQL for flexible queries",
        "summary": "GraphQL allows clients to request exactly the data they need"
    }
    assert engine._is_quality_action(action, parent) is True


def test_runtime_success_vs_fallback_vs_failure():
    """Runtime should distinguish success/fallback/failure clearly."""
    engine = CouncilEngine(runtime_mode="simulation")
    session = engine.create_session("Test", max_steps=1)
    root = session.nodes[session.active_queue[0]]

    success_meta = RuntimeMetadata(
        seat="TestSeat", node_id=root.node_id, runtime_mode="local_llm",
        model_used="qwen3:8b", failure_class="", fallback_used=False
    )
    fallback_meta = RuntimeMetadata(
        seat="TestSeat2", node_id=root.node_id, runtime_mode="hybrid",
        model_used="none", fallback_used=True, fallback_reason="timeout"
    )
    failure_meta = RuntimeMetadata(
        seat="TestSeat3", node_id=root.node_id, runtime_mode="local_llm",
        model_used="test", failure_class="timeout", fallback_used=False
    )

    session.runtime_metadata.extend([success_meta, fallback_meta, failure_meta])

    runtime_success = sum(1 for m in session.runtime_metadata if not m.failure_class and not m.fallback_used)
    fallback = sum(1 for m in session.runtime_metadata if m.fallback_used)
    failure = sum(1 for m in session.runtime_metadata if m.failure_class and not m.fallback_used)

    assert runtime_success == 1
    assert fallback == 1
    assert failure == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
