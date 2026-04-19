from __future__ import annotations
from typing import Dict, List, Optional, Set, Any
from dataclasses import field

from core.enums import (
    NodeType,
    NodeStatus,
    ResolutionState,
    SeatHealth,
    FinalPosture,
    ViewMode,
    GravityStage,
    IdeaPhase,
)
from core.models import (
    Session,
    Node,
    SeatAction,
    SeatState,
    SeatProfile,
    SessionArtifact,
    IdeaArtifact,
    SimulationParams,
    Motion,
    RoundRecord,
    clamp,
    sanitize_seat_state,
)
from seats.seat_profiles import SEAT_PROFILES


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def lower_text(*parts: str) -> str:
    return " ".join(p for p in parts if p).lower()


class CouncilEngine:
    def __init__(
        self,
        seat_profiles: Dict[str, SeatProfile] = None,
        params: SimulationParams = None,
        runtime_mode: str = "simulation",
    ):
        self.seat_profiles = seat_profiles or SEAT_PROFILES
        self.params = params or SimulationParams()
        validation_errors = self.params.validate()
        if validation_errors:
            raise ValueError(f"Invalid SimulationParams: {validation_errors}")

        # Runtime integration
        try:
            from seats.runtime import SeatRuntime

            self.runtime = SeatRuntime(mode=runtime_mode)
            self.runtime_mode = runtime_mode
        except ImportError:
            self.runtime = None
            self.runtime_mode = "simulation"

    def create_session(
        self, topic: str, max_steps: int = 50, mode: ViewMode = ViewMode.COUNCIL
    ) -> Session:
        session = Session(topic=topic, max_steps=max_steps, mode=mode.value)
        for name in self.seat_profiles:
            session.seat_states[name] = SeatState()

        root = Node(
            node_id=session.next_node_id(),
            node_type=NodeType.TOPIC,
            title=topic,
            summary=topic,
            parent_id=None,
            created_by="system",
            depth=0,
            linked_seats=list(self.seat_profiles.keys()),
            confidence=0.72,
            gravity=self.topic_gravity(topic),
        )
        session.nodes[root.node_id] = root
        session.active_queue.append(root.node_id)
        session.add_event(
            "session_created", f"Root topic: {topic}", node_id=root.node_id
        )
        return session

    def _update_identity_states(self, session: Session) -> None:
        """Update chair identity states after each step."""
        params = self.params
        for seat_name, state in session.seat_states.items():
            profile = self.seat_profiles.get(
                seat_name,
                SeatProfile(
                    name=seat_name,
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
                ),
            )
            memory_weight = getattr(profile, "memory_weight", 0.3)
            frustration_threshold = params.frustration_threshold
            fatigue_rate = params.fatigue_rate

            current_round = session.step_count
            last_round = getattr(state, "last_interaction_round", 0)
            rounds_since_last = current_round - last_round
            if rounds_since_last > 3:
                state.frustration = min(1.0, state.frustration + fatigue_rate)

            has_interactions = len(state.interaction_memory) > 0
            if has_interactions and memory_weight > 0:
                decay = 1.0 - memory_weight
                state.confidence = clamp(state.confidence * decay + 0.65 * (1 - decay))

            if len(state.contradiction_hits) >= params.contradiction_hits_threshold:
                state.frustration = min(1.0, state.frustration + fatigue_rate * 2)

            state.momentum = clamp(state.momentum - params.trust_decay)
            if state.frustration > frustration_threshold:
                state.momentum = min(1.0, state.momentum + 0.1)

            state.last_interaction_round = current_round

            sanitize_seat_state(state)

    def topic_gravity(self, topic: str) -> float:
        text = lower_text(topic)
        high_gravity = [
            "security",
            "failure",
            "critical",
            "bug",
            "death",
            "crash",
            "urgent",
            "emergency",
        ]
        medium_gravity = ["design", "architecture", "api", "performance", "scalability"]
        for kw in high_gravity:
            if kw in text:
                return 0.8
        for kw in medium_gravity:
            if kw in text:
                return 0.65
        return 0.5

    def run(self, session: Session) -> SessionArtifact:
        if session.mode == "idea":
            return self.run_idea_mode(session)
        if session.mode == "open":
            return self.run_open_discussion(session)

        while session.active_queue and session.step_count < session.max_steps:
            node_id = self.pick_next_node(session)
            if not node_id:
                break
            node = session.nodes[node_id]
            session.step_count += 1
            session.add_event(
                "active_node", f"Processing: {node.title}", node_id=node_id
            )
            self.process_node(session, node)
            if session.contradiction_pressure_enabled and self.should_pressure(node):
                self.run_contradiction_pressure(session, node)
            self.try_resolve_node(session, node)
            self._update_identity_states(session)
            self.refresh_queue(session)

        root = self.get_root(session)
        self.force_root_resolution_if_needed(session, root)
        self.run_identity_audit(session)
        self._emit_round_record(session)
        return self.build_artifact(session)

    def _emit_round_record(self, session: Session) -> None:
        """Emit round record at end of simulation."""
        active_node_ids = list(session.active_queue)
        completed_actions = [
            e.detail for e in session.replay[-20:] if e.event_type == "action_applied"
        ]
        contradictions_raised = list(session.contradictions)
        motion_ids = [m.node_id for m in session.motions]

        summary = f"Round {session.step_count}: {len(session.nodes)} nodes, {len(contradictions_raised)} contrad, {len(motion_ids)} motions"

        navigator_state = {
            "step_count": session.step_count,
            "active_nodes": len(active_node_ids),
            "total_nodes": len(session.nodes),
            "contradiction_pressure": len(contradictions_raised),
            "gravity_stage": session.nodes[session.active_queue[0]].gravity_stage.value
            if active_node_ids
            else None,
        }

        record = RoundRecord(
            round=session.step_count,
            active_nodes=active_node_ids,
            completed_actions=completed_actions,
            contradictions_raised=contradictions_raised,
            motions_proposed=motion_ids,
            chamber_summary=summary,
            navigator_state=navigator_state,
        )
        session.round_history.append(record)

    def run_open_discussion(self, session: Session) -> SessionArtifact:
        """Run Open Discussion mode - bounded exploratory deliberation."""
        from core.models import OpenDiscussionState, CandidateMotion

        session.open_discussion = OpenDiscussionState()
        session.contradiction_pressure_enabled = False

        while session.active_queue and session.step_count < session.max_steps:
            node_id = self.pick_next_node(session)
            if not node_id:
                break
            node = session.nodes[node_id]
            session.step_count += 1
            session.add_event(
                "open_discussion", f"Exploring: {node.title}", node_id=node_id
            )

            candidate = CandidateMotion(
                node_id=node.node_id,
                title=node.title,
                proposer=node.created_by,
                status="exploratory",
                support_count=len(node.supports),
                objection_count=len(node.objections),
            )
            if len(session.open_discussion.candidate_lines) < 10:
                session.open_discussion.candidate_lines.append(candidate)

            self.process_node(session, node)
            self._update_identity_states(session)

            if session.step_count % 3 == 0:
                self._narrowing_pulse(session)

            self._collect_open_contradictions(session, node)

            self.refresh_queue(session)

        self._rank_candidates(session)
        root = self.get_root(session)
        self.force_root_resolution_if_needed(session, root)
        self._emit_round_record(session)
        return self.build_artifact(session)

    def exit_open_discussion(
        self, session: Session, node_id: str, exit_type: str
    ) -> dict:
        """Exit Open Discussion mode with an explicit action."""
        valid_exits = {"promote", "defer", "split", "discard"}
        if exit_type not in valid_exits:
            return {"success": False, "reason": f"invalid_exit_type"}

        node = session.nodes.get(node_id)
        if not node:
            return {"success": False, "reason": "node_not_found"}

        if exit_type == "promote":
            session.motions.append(
                Motion(
                    node_id=node_id,
                    motion_type="promotion",
                    proposer=node.created_by,
                    stage=node.gravity_stage.value,
                    outcome="pending",
                    round=session.step_count,
                )
            )
        elif exit_type == "defer":
            node.resolution_state = ResolutionState.DEFERRED
        elif exit_type == "discard":
            node.status = NodeStatus.DEAD

        session.add_event(
            "exit_open_discussion",
            f"Exit to {exit_type}: {node.title}",
            node_id=node_id,
        )

        if exit_type == "split":
            return self._split_candidate(session, node_id)

        return {"success": True, "exit_type": exit_type, "node_id": node_id}

    def _collect_open_contradictions(self, session: Session, node: Node) -> None:
        """Collect lighter contradictions in Open Discussion mode."""
        objections = [o for o in node.objections if o]
        if objections and len(objections) >= 2:
            entry_id = f"open-contradiction-{session.step_count}"
            session.contradiction_ledger[entry_id] = {
                "source_node": node.node_id,
                "summary": f"Open discussion tension: {node.title}",
                "status": "advisory",
                "severity": "lighter",
            }
            session.contradictions.append(entry_id)

    def _split_candidate(self, session: Session, node_id: str) -> dict:
        """Split a candidate into follow-on candidates."""
        from core.models import CandidateMotion

        node = session.nodes.get(node_id)
        if not node:
            return {"success": False, "reason": "node_not_found"}

        child_ids = []
        titles = [f"{node.title} (Option A)", f"{node.title} (Option B)"]
        for i, title in enumerate(titles):
            child = Node(
                node_id=session.next_node_id(),
                node_type=NodeType.ALTERNATIVE,
                title=title,
                summary=f"Split from {node.title}",
                parent_id=node.node_id,
                created_by=node.created_by,
                depth=node.depth + 1,
            )
            session.nodes[child.node_id] = child
            child_ids.append(child.node_id)
            if (
                session.open_discussion
                and len(session.open_discussion.candidate_lines) < 10
            ):
                session.open_discussion.candidate_lines.append(
                    CandidateMotion(
                        node_id=child.node_id,
                        title=child.title,
                        proposer=child.created_by,
                        status="exploratory",
                    )
                )

        node.status = NodeStatus.DEAD
        return {
            "success": True,
            "exit_type": "split",
            "node_id": node_id,
            "child_ids": child_ids,
        }

    def _narrowing_pulse(self, session: Session) -> None:
        """Rank candidate lines and identify unresolved questions."""
        if not session.open_discussion:
            return

        session.open_discussion.narrowing_round += 1
        active_nodes = [
            n for n in session.nodes.values() if n.status == NodeStatus.ACTIVE
        ]

        ranked = sorted(
            active_nodes,
            key=lambda n: (len(n.supports), -len(n.objections), -n.gravity),
            reverse=True,
        )

        top_node_ids = [n.node_id for n in ranked[:3]]
        session.open_discussion.top_candidates = top_node_ids

        if ranked:
            for i, node_id in enumerate(top_node_ids):
                candidate = (
                    session.open_discussion.candidate_lines[i]
                    if i < len(session.open_discussion.candidate_lines)
                    else None
                )
                if candidate:
                    candidate.rank = i + 1

        unresolved = [
            n.title for n in active_nodes if len(n.objections) > len(n.supports)
        ]
        session.open_discussion.unresolved_questions = unresolved[:3]

        session.add_event(
            "narrowing_pulse",
            f"Round {session.open_discussion.narrowing_round}: {len(top_node_ids)} candidates, {len(unresolved)} unresolved",
        )

    def _rank_candidates(self, session: Session) -> None:
        """Final ranking of candidate motions."""
        if not session.open_discussion:
            return

        active = [n for n in session.nodes.values() if n.status == NodeStatus.ACTIVE]
        for candidate in session.open_discussion.candidate_lines:
            node = session.nodes.get(candidate.node_id)
            if node:
                candidate.support_count = len(node.supports)
                candidate.objection_count = len(node.objections)

    def run_idea_mode(self, session: Session) -> SessionArtifact:
        session.formal_session = True
        phases = [
            IdeaPhase.SEED,
            IdeaPhase.MUTATE,
            IdeaPhase.MASHUP,
            IdeaPhase.SALVAGE,
            IdeaPhase.PRESSURE,
        ]
        for phase in phases:
            session.idea_phase = phase.value
            session.add_event("idea_phase", f"Phase: {phase.value}")

            if phase == IdeaPhase.PRESSURE:
                self.idea_critique_phase(session)
            else:
                self.idea_generation_phase(session, phase)

        # After idea mode, run formal session mechanics
        self.run_formal_session(session)

        return self.build_artifact(session)

    def run_formal_session(self, session: Session) -> None:
        root = self.get_root(session)

        # === PHASE 1: Opening Statements ===
        for seat_name, profile in self.seat_profiles.items():
            state = session.seat_states[seat_name]
            # Each seat declares initial position
            stance = self._get_seat_stance(session, root, seat_name)
            statement = f"[{seat_name}] {stance}"
            session.opening_statements.append(statement)

            session.add_event(
                "opening_statement",
                statement,
                seat=seat_name,
            )

        # === PHASE 2: Challenge Round ===
        for node in session.nodes.values():
            if node.status.value in {"active", "contested"}:
                if len(node.objections) > len(node.supports):
                    finding = f"CHALLENGE: {node.title[:50]} has {len(node.objections)} objections vs {len(node.supports)} supports"
                    session.challenge_round_findings.append(finding)
                    session.add_event("challenge_round", finding, node_id=node.node_id)

                    # Generate minority report for this node
                    objection_seats = ", ".join(node.objections[:3])
                    session.minority_reports[node.node_id] = (
                        f"Minority ({objection_seats}): {node.title[:60]}"
                    )

        # === PHASE 3: Contradiction Harvest ===
        self._harvest_contradictions(session)

        # === PHASE 4: Final Posture ===
        self._capture_final_postures(session, root)

        # === PHASE 5: Locked Merger Artifact ===
        self._build_locked_artifact(session, root)

        session.add_event(
            "formal_session_complete",
            f"Formal session: {len(session.opening_statements)} openings, {len(session.challenge_round_findings)} challenges, {len(session.contradiction_ledger)} contradictions, {len(session.minority_reports)} minority reports",
        )

    def _get_seat_stance(self, session: Session, node: Node, seat: str) -> str:
        """Get seat's declared stance on a node."""
        if seat == "Strategist":
            return f"Focused on decision structure. Need clear trade-offs for {node.title}."
        elif seat == "Architect":
            return f"Concerned with system boundaries. Is {node.title} properly scoped?"
        elif seat == "Researcher":
            return (
                f"Exploring alternatives. What other approaches exist for {node.title}?"
            )
        elif seat == "Operator":
            return f"Practical focus. What's the minimum viable path for {node.title}?"
        elif seat == "Skeptic":
            return f"Questioning certainty. Hidden contradictions may exist in {node.title}."
        return f"Position on {node.title}"

    def _harvest_contradictions(self, session: Session) -> None:
        """Harvest and categorize contradictions with status."""
        harvest = []

        for entry in session.contradiction_ledger.values():
            status = entry.get("status", "open")
            target = entry.get("target_node_id", "")
            target_node = session.nodes.get(target)

            if target_node:
                target_title = target_node.title[:40]
            else:
                target_title = "unknown"

            entry_summary = entry.get("summary", "")[:50]
            risk = entry.get("risk_if_ignored", [])
            risk_str = risk[0][:40] if risk else ""

            harvest.append(
                {
                    "id": entry.get("id"),
                    "status": status,
                    "target": target_title,
                    "summary": entry_summary,
                    "risk": risk_str,
                }
            )

        # Categorize by status
        open_c = [h for h in harvest if h["status"] == "open"]
        narrowed_c = [h for h in harvest if h["status"] == "narrowed"]
        merged_c = [h for h in harvest if h["status"] == "merged"]
        resolved_c = [h for h in harvest if h["status"] == "resolved"]
        unresolved_c = [h for h in harvest if h["status"] == "unresolved"]
        deferred_c = [h for h in harvest if h["status"] == "deferred"]

        # Store as session-level harvest
        session.challenge_round_findings.append(f"--- CONTRADICTION HARVEST ---")
        session.challenge_round_findings.append(
            f"Open: {len(open_c)}, Narrowed: {len(narrowed_c)}, Merged: {len(merged_c)}, "
            f"Resolved: {len(resolved_c)}, Unresolved: {len(unresolved_c)}, Deferred: {len(deferred_c)}"
        )

        # Add detailed entries
        for h in harvest:
            session.challenge_round_findings.append(
                f"  [{h['status'][:3].upper()}] {h['target']}: {h['summary']}"
            )

        # Also add to risk_if_ignored if any unresolved or open
        if len(open_c) + len(unresolved_c) > 0:
            total_risk = len(open_c) + len(unresolved_c)
            session.risk_if_ignored.append(
                f"⚠ {total_risk} active contradictions require attention"
            )

    def _capture_final_postures(self, session: Session, root: Node) -> None:
        """Capture each seat's final posture."""
        from core.enums import FinalPosture

        for seat_name, profile in self.seat_profiles.items():
            state = session.seat_states[seat_name]

            # Determine posture based on seat's accumulated state
            if (
                len(root.objections) > len(root.supports)
                and seat_name in root.objections
            ):
                posture = FinalPosture.STAND.value
            elif state.concessions > 3:
                posture = FinalPosture.REVISE.value
            elif state.last_posture:
                posture = state.last_posture
            else:
                # Default based on seat type
                if seat_name == "Skeptic":
                    posture = FinalPosture.STAND.value  # Skeptic tends to stand
                elif seat_name == "Operator":
                    posture = (
                        FinalPosture.STAND.value
                    )  # Operator commits to practical path
                else:
                    posture = FinalPosture.ABSTAIN.value

            # Store in node and session
            root.final_postures[seat_name] = posture

            session.add_event(
                "final_posture",
                f"[{seat_name}] Final posture: {posture}",
                seat=seat_name,
            )

    def _build_locked_artifact(self, session: Session, root: Node) -> None:
        """Build the locked merger artifact with all formal outputs."""
        # This finalizes the session with complete structured output
        artifact_notes = []

        # Summary of consensus
        consensus = [
            n.title
            for n in session.nodes.values()
            if n.resolution_state and n.resolution_state.value in {"accepted", "merged"}
        ]
        if consensus:
            artifact_notes.append(f"ACCEPTED: {', '.join(consensus[:3])}")

        # Summary of unresolved
        unresolved = [
            n.title
            for n in session.nodes.values()
            if n.resolution_state and n.resolution_state.value == "unresolved"
        ]
        if unresolved:
            artifact_notes.append(f"UNRESOLVED: {', '.join(unresolved[:3])}")

        # Minority position preserved
        minority_cnt = len(session.minority_reports)
        if minority_cnt > 0:
            artifact_notes.append(
                f"MINORITY OBJECTIONS: {minority_cnt} preserved in final artifact"
            )

        # Risk summary
        risk_cnt = len(session.risk_if_ignored)
        if risk_cnt > 0:
            artifact_notes.append(f"RISK-IF-IGNORED: {risk_cnt} items noted")

        # Final posture summary
        postures = [f"{k}:{v}" for k, v in root.final_postures.items()]
        artifact_notes.append(f"FINAL POSTURES: {' '.join(postures)}")

        # Store as session-level final output
        session.last_outputs["locked_artifact"] = "\n".join(artifact_notes)

    def idea_generation_phase(self, session: Session, phase: IdeaPhase) -> None:
        root = self.get_root(session)

        if phase == IdeaPhase.SEED:
            seed = Node(
                node_id=session.next_node_id(),
                node_type=NodeType.IDEA_SEED,
                title=f"Seed: {root.title}",
                summary=f"Core concept for {root.title}",
                parent_id=root.node_id,
                created_by="Researcher",
                depth=root.depth + 1,
                confidence=0.7,
                gravity=0.4,
            )
            session.nodes[seed.node_id] = seed
            root.children.append(seed.node_id)
            session.idea_artifacts.best_raw_ideas.append(
                f"Seed: {root.title} - core concept"
            )

        elif phase == IdeaPhase.MUTATE:
            mutation = Node(
                node_id=session.next_node_id(),
                node_type=NodeType.TWIST,
                title=f"Twist: Alternative framing of {root.title}",
                summary=f"Mutated version with different angle",
                parent_id=root.node_id,
                created_by="Strategist",
                depth=root.depth + 1,
                confidence=0.6,
                gravity=0.45,
            )
            session.nodes[mutation.node_id] = mutation
            root.children.append(mutation.node_id)
            session.idea_artifacts.best_raw_ideas.append(
                f"Twist: Alternative framing of {root.title}"
            )

        elif phase == IdeaPhase.MASHUP:
            mashup = Node(
                node_id=session.next_node_id(),
                node_type=NodeType.MASHUP,
                title=f"Mashup: {root.title} + practical implementation",
                summary="Combining with real-world constraints",
                parent_id=root.node_id,
                created_by="Operator",
                depth=root.depth + 1,
                confidence=0.55,
                gravity=0.5,
            )
            session.nodes[mashup.node_id] = mashup
            root.children.append(mashup.node_id)
            session.idea_artifacts.best_mashups.append(
                f"Mashup: {root.title} + implementation"
            )

        elif phase == IdeaPhase.SALVAGE:
            salvage = Node(
                node_id=session.next_node_id(),
                node_type=NodeType.SALVAGE,
                title=f"Salvage: Usable parts from {root.title}",
                summary="Extract what's still useful",
                parent_id=root.node_id,
                created_by="Architect",
                depth=root.depth + 1,
                confidence=0.5,
                gravity=0.35,
            )
            session.nodes[salvage.node_id] = salvage
            root.children.append(salvage.node_id)
            session.idea_artifacts.best_salvage.append(
                f"Salvage: Usable parts from {root.title}"
            )

    def idea_critique_phase(self, session: Session) -> None:
        """Pressure phase: Skeptic applies hard critique to ideas."""
        root = self.get_root(session)

        # Skeptic applies hard scrutiny - this is the delayed critique
        skeptic_action = self._skeptic_action(session, root, None, root.gravity + 0.1)
        if skeptic_action:
            self.apply_action(session, root, skeptic_action)
            session.add_event(
                "idea_critique",
                f"Skeptic pressure: {skeptic_action.summary}",
                seat="Skeptic",
                node_id=root.node_id,
            )

        # Create experiment node
        experiment = Node(
            node_id=session.next_node_id(),
            node_type=NodeType.EXPERIMENT,
            title=f"Experiment: {root.title} under pressure",
            summary="Testing viability under hard scrutiny",
            parent_id=root.node_id,
            created_by="Skeptic",
            depth=root.depth + 1,
            confidence=0.4,
            gravity=0.7,
        )
        session.nodes[experiment.node_id] = experiment
        root.children.append(experiment.node_id)
        session.idea_artifacts.best_experiments.append(
            f"Test: {root.title} under pressure"
        )

    def process_node(self, session: Session, node: Node) -> None:
        for seat_name, profile in self.seat_profiles.items():
            if session.seat_states[seat_name].health in {
                SeatHealth.SUSPENDED,
                SeatHealth.KILLED,
            }:
                continue
            action = self.select_action(session, node, seat_name, profile)
            if action:
                self.apply_action(session, node, action)

        self.update_gravity(node)

    def select_action(
        self, session: Session, node: Node, seat_name: str, profile: SeatProfile
    ) -> Optional[SeatAction]:
        gravity = node.gravity
        if gravity < 0.18:
            return None

        node_type = node.node_type
        state = session.seat_states.get(seat_name)
        identity_strength = getattr(profile, "identity_strength", 0.5)
        self_assertion = getattr(state, "self_assertion", 0.5) if state else 0.5
        stubbornness = getattr(state, "stubbornness", 0.5) if state else 0.5
        trust_map = getattr(profile, "trust_map", {})

        if seat_name == "Strategist":
            action = self._strategist_action(session, node, profile, gravity)
            action = self._apply_trust_modifier(action, session, seat_name, trust_map)
            return self._apply_identity_modifier(
                action, identity_strength, self_assertion, stubbornness
            )
        elif seat_name == "Architect":
            action = self._architect_action(session, node, profile, gravity)
            action = self._apply_trust_modifier(action, session, seat_name, trust_map)
            action = self._apply_preferred_mode(action, profile)
            return self._apply_identity_modifier(
                action, identity_strength, self_assertion, stubbornness
            )
        elif seat_name == "Researcher":
            action = self._researcher_action(session, node, profile, gravity)
            action = self._apply_trust_modifier(action, session, seat_name, trust_map)
            action = self._apply_preferred_mode(action, profile)
            return self._apply_identity_modifier(
                action, identity_strength, self_assertion, stubbornness
            )
        elif seat_name == "Operator":
            action = self._operator_action(session, node, profile, gravity)
            action = self._apply_trust_modifier(action, session, seat_name, trust_map)
            return self._apply_identity_modifier(
                action, identity_strength, self_assertion, stubbornness
            )
        elif seat_name == "Skeptic":
            action = self._skeptic_action(session, node, profile, gravity)
            action = self._apply_trust_modifier(action, session, seat_name, trust_map)
            action = self._apply_preferred_mode(action, profile)
            return self._apply_identity_modifier(
                action, identity_strength, self_assertion, stubbornness
            )

        return None

    def _apply_trust_modifier(
        self,
        action: Optional[SeatAction],
        session: Session,
        seat_name: str,
        trust_map: Dict[str, float],
    ) -> Optional[SeatAction]:
        """Apply trust_map influence from other seats."""
        if action is None or not trust_map:
            return action

        total_trust = 0.0
        weighted_sum = 0.0
        for other_seat, trust in trust_map.items():
            if trust > 0:
                other_state = session.seat_states.get(other_seat)
                if other_state and other_state.health != SeatHealth.KILLED:
                    total_trust += trust
                    trust_influence = trust * (other_state.confidence - 0.5)
                    weighted_sum += trust_influence

        if total_trust > 0 and abs(weighted_sum) > 0.05:
            trust_bias = weighted_sum / total_trust * 0.15
            action.confidence = clamp(action.confidence + trust_bias)
            action.summary = f"[trust-influenced] {action.summary}"

        return action

    def _apply_preferred_mode(
        self, action: Optional[SeatAction], profile: SeatProfile
    ) -> Optional[SeatAction]:
        """Apply preferred mode bias to action selection."""
        if action is None:
            return action

        pref_attack = getattr(profile, "preferred_attack_modes", [])
        pref_refine = getattr(profile, "preferred_refinement_modes", [])

        action_type = action.action_type
        has_preference = False
        if action_type == "object" and pref_attack:
            action.confidence *= 1.05
            action.summary = f"[attack:{pref_attack[0]}] {action.summary}"
            has_preference = True
        elif action_type == "refinement" and pref_refine:
            action.confidence *= 1.05
            action.summary = f"[refine:{pref_refine[0]}] {action.summary}"
            has_preference = True

        return action

    def _apply_identity_modifier(
        self,
        action: Optional[SeatAction],
        identity_strength: float,
        self_assertion: float,
        stubbornness: float,
    ) -> Optional[SeatAction]:
        """Apply identity dynamics to action confidence."""
        if action is None:
            return None
        identity_factor = 1.0 + (identity_strength - 0.5) * 0.3
        assertion_factor = 1.0 + (self_assertion - 0.5) * 0.2
        stubborn_factor = 1.0 + (stubbornness - 0.5) * 0.15
        combined_factor = identity_factor * assertion_factor * stubborn_factor
        action.confidence = clamp(action.confidence * combined_factor)
        return action

    def _strategist_action(
        self, session: Session, node: Node, profile: SeatProfile, gravity: float
    ) -> Optional[SeatAction]:
        """Strategist: pushes narrowing, clarity, decision shape."""
        if node.node_type == NodeType.TOPIC:
            return SeatAction(
                seat="Strategist",
                node_id=node.node_id,
                action_type="claim",
                title=f"[STRATEGIST] Decision framing: {node.title}",
                summary="Framing as decision point with clear trade-offs",
                confidence=0.7,
            )
        elif node.node_type == NodeType.CLAIM:
            if len(node.alternatives) > 1:
                return SeatAction(
                    seat="Strategist",
                    node_id=node.node_id,
                    action_type="refinement",
                    title=f"[STRATEGIST] Narrow to top 2 options",
                    summary="Too many paths - narrow decision space",
                    confidence=0.65,
                )
            return SeatAction(
                seat="Strategist",
                node_id=node.node_id,
                action_type="support",
                title=f"[STRATEGIST] Clear direction",
                summary="This provides actionable direction",
                confidence=0.6,
            )
        elif node.node_type == NodeType.ALTERNATIVE:
            return SeatAction(
                seat="Strategist",
                node_id=node.node_id,
                action_type="refinement",
                title=f"[STRATEGIST] Explicit escalation path",
                summary="Need clear escalation if this fails",
                confidence=0.55,
            )
        return None

    def _architect_action(
        self, session: Session, node: Node, profile: SeatProfile, gravity: float
    ) -> Optional[SeatAction]:
        """Architect: attacks mixed layers, vague boundaries."""
        if node.node_type == NodeType.TOPIC:
            return SeatAction(
                seat="Architect",
                node_id=node.node_id,
                action_type="claim",
                title=f"[ARCHITECT] Boundary clarification: {node.title}",
                summary="Defining clear system boundaries and interfaces",
                confidence=0.7,
            )
        elif node.node_type == NodeType.CLAIM:
            if len(node.refinements) == 0 and len(node.children) > 2:
                return SeatAction(
                    seat="Architect",
                    node_id=node.node_id,
                    action_type="object",
                    title=f"[ARCHITECT] Mixed layers",
                    summary="This conflates multiple abstraction layers",
                    confidence=0.7,
                )
            return SeatAction(
                seat="Architect",
                node_id=node.node_id,
                action_type="refinement",
                title=f"[ARCHITECT] Clarify boundary",
                summary="Need clearer interface definition",
                confidence=0.6,
            )
        return None

    def _researcher_action(
        self, session: Session, node: Node, profile: SeatProfile, gravity: float
    ) -> Optional[SeatAction]:
        """Researcher: keeps options open, introduces cross-domain ideas."""
        if node.node_type == NodeType.TOPIC:
            return SeatAction(
                seat="Researcher",
                node_id=node.node_id,
                action_type="alternative",
                title=f"[RESEARCHER] Alternative framing: {node.title}",
                summary="Consider this from comparative perspective",
                confidence=0.65,
            )
        elif gravity < 0.5 and node.node_type in {NodeType.CLAIM, NodeType.ALTERNATIVE}:
            return SeatAction(
                seat="Researcher",
                node_id=node.node_id,
                action_type="alternative",
                title=f"[RESEARCHER] Another angle",
                summary="What about approach X vs Y?",
                confidence=0.55,
            )
        elif node.node_type == NodeType.CLAIM:
            return SeatAction(
                seat="Researcher",
                node_id=node.node_id,
                action_type="support",
                title=f"[RESEARCHER] Evidence noted",
                summary="This aligns with patterns from domain",
                confidence=0.5,
            )
        return None

    def _operator_action(
        self, session: Session, node: Node, profile: SeatProfile, gravity: float
    ) -> Optional[SeatAction]:
        """Operator: kills overbuilt ideas, prefers minimum viable."""
        if node.node_type == NodeType.TOPIC:
            return SeatAction(
                seat="Operator",
                node_id=node.node_id,
                action_type="claim",
                title=f"[OPERATOR] Practical path: {node.title}",
                summary="What's the minimum viable implementation?",
                confidence=0.7,
            )
        elif node.node_type in {NodeType.CLAIM, NodeType.ALTERNATIVE}:
            if len(node.children) > 3 or len(node.refinements) > 2:
                return SeatAction(
                    seat="Operator",
                    node_id=node.node_id,
                    action_type="object",
                    title=f"[OPERATOR] Overbuilt",
                    summary="Too complex - what's the simplest path?",
                    confidence=0.75,
                )
            return SeatAction(
                seat="Operator",
                node_id=node.node_id,
                action_type="alternative",
                title=f"[OPERATOR] Simpler alternative",
                summary="Can we achieve this with less?",
                confidence=0.6,
            )
        return None

    def _skeptic_action(
        self, session: Session, node: Node, profile: SeatProfile, gravity: float
    ) -> Optional[SeatAction]:
        """Skeptic: preserves dissent, pressures weak claims."""
        # In idea mode, hold back until pressure phase
        if session.idea_phase and session.idea_phase != "pressure":
            return None

        if node.node_type == NodeType.TOPIC:
            return SeatAction(
                seat="Skeptic",
                node_id=node.node_id,
                action_type="object",
                title=f"[SKEPTIC] Question premise: {node.title}",
                summary="Is this even the right question?",
                confidence=0.6,
            )
        elif node.node_type == NodeType.CLAIM:
            if node.confidence > 0.8 and len(node.objections) == 0:
                return SeatAction(
                    seat="Skeptic",
                    node_id=node.node_id,
                    action_type="object",
                    title=f"[SKEPTIC] False certainty",
                    summary="Too confident - where's the contradiction?",
                    confidence=0.85,
                )
            if gravity > 0.6:
                return SeatAction(
                    seat="Skeptic",
                    node_id=node.node_id,
                    action_type="object",
                    title=f"[SKEPTIC] Pressure test failed",
                    summary="This doesn't survive hard scrutiny",
                    confidence=0.7,
                )
        return None

    def apply_action(self, session: Session, node: Node, action: SeatAction) -> None:
        if action.action_type == "support":
            node.supports.append(action.seat)
            node.stance_map[action.seat] = "support"
        elif action.action_type == "object":
            node.objections.append(action.seat)
            node.stance_map[action.seat] = "object"
            session.seat_states[action.seat].objections_made += 1
        elif action.action_type == "claim":
            # Create real child node
            child = self._create_child_node(
                session,
                node,
                action.title or action.summary or "New claim",
                action.summary or f"Claim by {action.seat}",
                NodeType.CLAIM,
            )
            node.children.append(child.node_id)
        elif action.action_type == "refinement":
            node.refinements.append(action.seat)
            # Also create refinement child
            child = self._create_child_node(
                session,
                node,
                f"Refinement: {action.title or node.title[:30]}",
                action.summary or f"Refinement by {action.seat}",
                NodeType.REFINEMENT,
            )
            node.children.append(child.node_id)
        elif action.action_type == "alternative":
            node.alternatives.append(action.seat)
            # Create alternative child
            alt = self._create_child_node(
                session,
                node,
                f"Alternative: {action.title or node.title[:30]}",
                action.summary or f"Alternative by {action.seat}",
                NodeType.ALTERNATIVE,
            )
            node.children.append(alt.node_id)
        elif action.action_type == "evidence_needed":
            child = self._create_child_node(
                session,
                node,
                f"Evidence: {action.title or node.title[:30]}",
                action.summary or f"Evidence needed by {action.seat}",
                NodeType.EVIDENCE,
            )
            node.children.append(child.node_id)

    def _create_child_node(
        self,
        session: Session,
        parent: Node,
        title: str,
        summary: str,
        node_type: NodeType,
    ) -> Node:
        """Create a real child node."""
        child = Node(
            node_id=session.next_node_id(),
            node_type=node_type,
            title=title[:120],
            summary=summary[:250],
            parent_id=parent.node_id,
            created_by=parent.created_by,
            depth=parent.depth + 1,
            linked_seats=parent.linked_seats.copy(),
            confidence=parent.confidence * 0.9,
            gravity=max(0.15, parent.gravity - 0.05),
        )
        session.nodes[child.node_id] = child
        session.active_queue.append(child.node_id)
        session.add_event(
            "node_created", f"{node_type.value}: {title[:50]}", node_id=child.node_id
        )
        return child

    def update_gravity(self, node: Node) -> None:
        activity = len(node.objections) + len(node.supports) + len(node.refinements)
        node.gravity = clamp(node.gravity + (activity * 0.05))

        if node.gravity >= 0.75:
            node.gravity_stage = GravityStage.TRIBUNAL
        elif node.gravity >= 0.6:
            node.gravity_stage = GravityStage.FORMAL
        elif node.gravity >= 0.45:
            node.gravity_stage = GravityStage.ADVISORY
        else:
            node.gravity_stage = GravityStage.EXPLORATORY

    def run_contradiction_pressure(self, session: Session, node: Node) -> None:
        challenger = "Skeptic"
        if session.seat_states[challenger].health == SeatHealth.KILLED:
            return
        text = f"Pressure: {node.title} may be wrong"
        session.add_event(
            "contradiction_pressure", text, seat=challenger, node_id=node.node_id
        )
        node.risk_if_ignored.append(text)
        session.risk_if_ignored.append(f"[{node.node_id}] {text}")
        session.seat_states[challenger].direct_challenges += 1

        # Record in contradiction ledger
        contradiction_id = f"c{len(session.contradiction_ledger) + 1}"
        session.contradiction_ledger[contradiction_id] = {
            "id": contradiction_id,
            "source_seat": challenger,
            "target_node_id": node.node_id,
            "summary": text,
            "status": "open",
            "risk_if_ignored": [text],
            "created_at": session.step_count,
        }

    def should_pressure(self, node: Node) -> bool:
        return (
            node.node_type in {NodeType.CLAIM, NodeType.REFINEMENT}
            and node.gravity > 0.55
            and len(node.children) > 1
        )

    def _update_contradiction_status(
        self, session, node_id: str, new_status: str
    ) -> None:
        """Update contradiction status in ledger."""
        for entry in session.contradiction_ledger.values():
            if entry["target_node_id"] == node_id:
                entry["status"] = new_status

    def _get_node_contradictions(self, session, node_id: str) -> list:
        """Get all contradictions for a node."""
        return [
            e
            for e in session.contradiction_ledger.values()
            if e["target_node_id"] == node_id
        ]

    def try_resolve_node(self, session: Session, node: Node) -> None:
        if node.node_type == NodeType.RESOLUTION or node.status in {
            NodeStatus.RESOLVED,
            NodeStatus.DEFERRED,
            NodeStatus.DEAD,
        }:
            return

        contr = len(node.objections)
        supp = len(node.supports)
        refin = len(node.refinements)
        alt = len(node.alternatives)

        # Alternative exists, no contradiction -> merge
        if alt > 0 and contr == 0:
            node.status = NodeStatus.RESOLVED
            node.resolution_state = ResolutionState.MERGED
            # Update contradiction status to merged
            self._update_contradiction_status(session, node.node_id, "merged")
            session.add_event(
                "node_merged", f"Merged: {node.title}", node_id=node.node_id
            )
            return

        # Open contradiction that gets resolved
        # Check both node objections AND contradiction ledger
        has_contradiction = (
            len(self._get_node_contradictions(session, node.node_id)) > 0
        )
        if has_contradiction:
            if refin > 0:
                # Narrowed - contradiction exists but got refinement
                self._update_contradiction_status(session, node.node_id, "narrowed")
            elif contr == 0 and supp > 0:
                # Supported - contradiction exists but has support
                self._update_contradiction_status(session, node.node_id, "resolved")

        if (
            contr == 0
            and alt == 0
            and refin == 0
            and (supp > 0 or node.node_type == NodeType.TOPIC)
        ):
            node.status = NodeStatus.RESOLVED
            node.resolution_state = ResolutionState.ACCEPTED
            session.add_event(
                "node_resolved", f"Accepted: {node.title}", node_id=node.node_id
            )

        if contr > 1 and supp == 0 and refin == 0:
            node.status = NodeStatus.RESOLVED
            node.resolution_state = ResolutionState.UNRESOLVED
            # Update contradiction status
            if has_contradiction:
                self._update_contradiction_status(session, node.node_id, "unresolved")
            session.add_event(
                "node_unresolved", f"Unresolved: {node.title}", node_id=node.node_id
            )

        # Check for deferred state (blocked by evidence need)
        if (
            len(node.evidence_requests) > 0
            and len(node.objections) > 0
            and len(node.supports) == 0
        ):
            node.status = NodeStatus.DEFERRED
            node.resolution_state = ResolutionState.DEFERRED
            if has_contradiction:
                self._update_contradiction_status(session, node.node_id, "deferred")
            session.add_event(
                "node_deferred",
                f"Deferred: {node.title} - evidence needed",
                node_id=node.node_id,
            )

    def force_root_resolution_if_needed(self, session: Session, root: Node) -> None:
        if root.resolution_state is not None:
            return
        unresolved = any(
            "unresolved_child" in n.tags
            for n in session.nodes.values()
            if n.parent_id == root.node_id
        )
        if unresolved:
            root.resolution_state = ResolutionState.UNRESOLVED
        else:
            root.resolution_state = ResolutionState.ACCEPTED
        root.status = NodeStatus.RESOLVED
        session.add_event(
            "root_resolved",
            f"Root: {root.resolution_state.value}",
            node_id=root.node_id,
        )

    def run_identity_audit(self, session: Session) -> None:
        for seat_name, state in session.seat_states.items():
            if state.concessions > 5:
                session.add_event(
                    "seat_degraded",
                    f"{seat_name} degraded from too many concessions",
                    seat=seat_name,
                )

    def refresh_queue(self, session: Session) -> None:
        kept = [
            nid
            for nid in session.active_queue
            if session.nodes[nid].status in {NodeStatus.ACTIVE, NodeStatus.CONTESTED}
        ]
        session.active_queue = kept

    def pick_next_node(self, session: Session) -> Optional[str]:
        candidates = [
            session.nodes[nid]
            for nid in session.active_queue
            if session.nodes[nid].status in {NodeStatus.ACTIVE, NodeStatus.CONTESTED}
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda n: (n.depth, -n.gravity, -len(n.objections), n.node_id)
        )
        return candidates[0].node_id

    def get_root(self, session: Session) -> Node:
        for node in session.nodes.values():
            if node.parent_id is None:
                return node
        raise RuntimeError("No root node")

    def _get_divergence_markers(self, session: Session) -> List[str]:
        """Get divergence/minority markers."""
        markers = []
        for node in session.nodes.values():
            if len(node.objections) > len(node.supports):
                markers.append(f"divergent:{node.node_id}")
        for entry_id, entry in session.contradiction_ledger.items():
            if entry.get("severity") == "lighter":
                markers.append(f"advisory:{entry_id}")
        return markers[:5]

    def build_artifact(self, session: Session) -> SessionArtifact:
        root = self.get_root(session)
        unresolved = [
            n.node_id
            for n in session.nodes.values()
            if n.resolution_state == ResolutionState.UNRESOLVED
        ]
        minorities = [
            f"{n.title}: {n.node_id}"
            for n in session.nodes.values()
            if len(n.objections) > len(n.supports)
        ]

        stage_counts = {}
        for node in session.nodes.values():
            stage = node.gravity_stage.value
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        promotions = [n.node_id for n in session.nodes.values() if n.promoted]
        rejected = [
            n.node_id
            for n in session.nodes.values()
            if n.gravity_stage == GravityStage.EXPLORATORY
            and len(n.promotion_votes) > 0
            and not n.promoted
        ]

        pending_reviews = [m.node_id for m in session.motions if m.outcome == "pending"]
        rejected_reviews = [
            m.node_id for m in session.motions if m.outcome in ("rejected", "deferred")
        ]

        return SessionArtifact(
            root_resolution=root.resolution_state,
            consensus_points=[
                n.title
                for n in session.nodes.values()
                if n.resolution_state == ResolutionState.ACCEPTED
            ],
            minority_objections=minorities,
            unresolved_branches=unresolved,
            contradictions=session.contradictions,
            keep=[root.title],
            remove=[],
            upgrade=[],
            branch_scores={n.node_id: n.gravity for n in session.nodes.values()},
            replay_event_count=len(session.replay),
            seat_drift={
                seat: state.lane_drift_flags
                for seat, state in session.seat_states.items()
            },
            final_postures={
                seat: state.last_posture or "none"
                for seat, state in session.seat_states.items()
            },
            mode=session.mode,
            gravity_stage_counts=stage_counts,
            promotions=promotions,
            rejected_promotions=rejected,
            review_items=[m.node_id for m in session.motions],
            pending_reviews=pending_reviews,
            rejected_reviews=rejected_reviews,
            open_discussion_active=session.mode == "open",
            candidate_motions=[
                c.node_id
                for c in (
                    session.open_discussion.candidate_lines
                    if session.open_discussion
                    else []
                )
            ],
            top_candidates=session.open_discussion.top_candidates
            if session.open_discussion
            else [],
            unresolved_questions=session.open_discussion.unresolved_questions
            if session.open_discussion
            else [],
            narrowing_round=session.open_discussion.narrowing_round
            if session.open_discussion
            else 0,
            divergence_markers=self._get_divergence_markers(session),
        )

    def vote_on_promotion(
        self, session: Session, node_id: str, seat: str, forced: bool = False
    ) -> dict:
        """Promotion vote with eligibility gate and full outcomes."""
        from core.models import validate_motion_stage_transition

        node = session.nodes.get(node_id)
        if not node:
            return {"success": False, "reason": "node_not_found"}

        next_stage = self._get_next_stage(node.gravity_stage)
        if not validate_motion_stage_transition(
            node.gravity_stage.value, next_stage.value
        ):
            return {"success": False, "reason": "invalid_stage_transition"}

        motion = Motion(
            node_id=node_id,
            motion_type="promotion",
            proposer=seat,
            stage=node.gravity_stage.value,
            outcome="pending",
            round=session.step_count,
        )
        session.motions.append(motion)

        # Track promotion votes
        if not hasattr(node, "promotion_votes"):
            node.promotion_votes = []
        if not hasattr(node, "promotion_record"):
            node.promotion_record = []

        vote_record = {
            "seat": seat,
            "from_stage": node.gravity_stage.value,
            "requested_stage": next_stage.value,
            "forced": forced,
            "timestamp": session.step_count,
        }
        node.promotion_record.append(vote_record)
        node.promotion_votes.append(seat)

        # === PHASE 1: ELIGIBILITY GATE ===
        eligibility = self._check_promotion_eligibility(session, node, seat)

        if not eligibility["eligible"]:
            session.add_event(
                "promotion_ineligible",
                f"Promotion rejected: {eligibility['reason']}",
                seat=seat,
            )
            motion.outcome = "rejected"
            return {
                "outcome": "reject",
                "eligible": False,
                "reason": eligibility["reason"],
                "evidence": eligibility.get("evidence", []),
            }

        # === PHASE 2: VOTE OUTCOME ===
        # Count votes
        total_seats = len(self.seat_profiles)
        votes_yes = len(node.promotion_votes)
        votes_needed = total_seats // 2 + 1  # Simple majority

        # Check for high-rigor seat support (Strategist, Architect, Skeptic)
        high_rigor_seats = {"Strategist", "Architect", "Skeptic"}
        has_high_rigor = any(v in high_rigor_seats for v in node.promotion_votes)

        # Apply stage-specific thresholds
        current_stage = node.gravity_stage

        if current_stage == GravityStage.EXPLORATORY:
            # Forced bypasses vote threshold
            if forced or votes_yes >= votes_needed:
                return self._execute_promotion(session, node, next_stage, forced, seat)
            else:
                return {
                    "outcome": "eligible_defer",
                    "votes": votes_yes,
                    "needed": votes_needed,
                }

        elif current_stage == GravityStage.ADVISORY:
            # Simple majority + high-rigor seat required OR forced bypass
            if forced or (votes_yes >= votes_needed and has_high_rigor):
                return self._execute_promotion(session, node, next_stage, forced, seat)
            elif votes_yes >= votes_needed and not has_high_rigor:
                return {
                    "outcome": "eligible_defer",
                    "reason": "requires_high_rigor_seat_support",
                }
            else:
                return {
                    "outcome": "eligible_defer",
                    "votes": votes_yes,
                    "needed": votes_needed,
                }

        elif current_stage == GravityStage.FORMAL:
            # Supermajority (2/3) + explicit justification + risk-if-not-promoted, OR forced bypass
            votes_needed = int(total_seats * 0.67)
            has_justification = len(getattr(node, "promotion_justification", "")) > 20
            has_risk = len(node.risk_if_ignored) > 0

            if forced or (votes_yes >= votes_needed and has_justification and has_risk):
                return self._execute_promotion(session, node, next_stage, forced, seat)
            else:
                reasons = []
                if votes_yes < votes_needed:
                    reasons.append(f"supermajority ({votes_yes}/{votes_needed})")
                if not has_justification:
                    reasons.append("needs_written_justification")
                if not has_risk:
                    reasons.append("needs_risk_if_not_promoted")
                return {"outcome": "eligible_defer", "reasons": reasons}

        return {"outcome": "eligible_defer", "votes": votes_yes}

    def _check_promotion_eligibility(
        self, session: Session, node: Node, seat: str
    ) -> dict:
        """Check if a branch is eligible for promotion."""
        checks = []
        evidence = []

        # 1. Bounded enough - has clear scope
        if node.title and len(node.title) > 3:
            checks.append(True)
            evidence.append("bounded_title")
        else:
            checks.append(False)
            evidence.append("vague_title")

        # 2. Survived meaningful pressure
        if len(getattr(node, "risk_if_ignored", [])) > 0:
            checks.append(True)
            evidence.append("survived_pressure")

        # 3. Gained structure or artifact value
        if node.children or node.refinements or node.resolution_state:
            checks.append(True)
            evidence.append("has_structure")

        # 4. Materially matters - has support or objections
        if node.supports or node.objections:
            checks.append(True)
            evidence.append("matters")
        else:
            # Still OK if has gravity
            if node.gravity > 0.5:
                checks.append(True)
                evidence.append("high_gravity")
            else:
                checks.append(False)
                evidence.append("noise_no_engagement")

        # 5. Not vanity - multiple seats involved OR has real consequence
        unique_seats = set(node.supports + node.objections)
        if len(unique_seats) >= 2 or node.gravity > 0.7:
            checks.append(True)
            evidence.append("not_vanity")
        else:
            checks.append(False)
            evidence.append("one_seat_vanity")

        # Anti-abuse: reject if contradiction-blind
        if (
            not node.objections
            and node.gravity > 0.5
            and len(session.contradiction_ledger) > 0
        ):
            checks.append(False)
            evidence.append("contradiction_blind")

        eligible = all(checks)

        return {
            "eligible": eligible,
            "reason": "failed_eligibility_checks" if not eligible else "eligible",
            "evidence": evidence,
        }

    def _get_next_stage(self, current: GravityStage) -> GravityStage:
        """Get the next gravity stage."""
        if current == GravityStage.EXPLORATORY:
            return GravityStage.ADVISORY
        elif current == GravityStage.ADVISORY:
            return GravityStage.FORMAL
        elif current == GravityStage.FORMAL:
            return GravityStage.TRIBUNAL
        return current

    def _get_prior_stage(self, current: GravityStage) -> GravityStage:
        """Get the prior gravity stage (for demotion)."""
        if current == GravityStage.TRIBUNAL:
            return GravityStage.FORMAL
        elif current == GravityStage.FORMAL:
            return GravityStage.ADVISORY
        elif current == GravityStage.ADVISORY:
            return GravityStage.EXPLORATORY
        return current

    def vote_on_demotion(
        self, session: Session, node_id: str, seat: str, reason: str = ""
    ) -> dict:
        """Vote on demotion of a branch to a lower gravity stage."""
        node = session.nodes.get(node_id)
        if not node:
            return {"success": False, "reason": "node_not_found"}

        if node.gravity_stage == GravityStage.EXPLORATORY:
            return {"outcome": "reject", "reason": "already_at_lowest_stage"}

        # Track demotion votes
        if not hasattr(node, "demotion_votes"):
            node.demotion_votes = []
        if not hasattr(node, "demotion_history"):
            node.demotion_history = []

        node.demotion_votes.append(seat)

        demotion_record = {
            "seat": seat,
            "from_stage": node.gravity_stage.value,
            "requested_stage": self._get_prior_stage(node.gravity_stage).value,
            "reason": reason,
            "timestamp": session.step_count,
        }
        node.demotion_history.append(demotion_record)

        # Check if enough votes for demotion
        total_seats = len(self.seat_profiles)
        votes_yes = len(node.demotion_votes)
        votes_needed = total_seats // 2 + 1  # Simple majority

        if votes_yes >= votes_needed:
            return self._execute_demotion(session, node, seat, reason)
        else:
            return {
                "outcome": "demotion_defer",
                "votes": votes_yes,
                "needed": votes_needed,
            }

    def _execute_demotion(
        self, session: Session, node: Node, seat: str, reason: str
    ) -> dict:
        """Execute the demotion."""
        old_stage = node.gravity_stage
        new_stage = self._get_prior_stage(old_stage)
        node.gravity_stage = new_stage

        # Record demotion in artifact
        node.demoted = True
        node.demoted_by = seat
        node.demotion_reason = reason

        session.add_event(
            "demotion_approved",
            f"Demotion: {node.title} {old_stage.value} -> {new_stage.value}",
            seat=seat,
        )

        return {
            "outcome": "demote_now",
            "old_stage": old_stage.value,
            "new_stage": new_stage.value,
            "demoted_by": seat,
            "reason": reason,
        }

    def _execute_promotion(
        self,
        session: Session,
        node: Node,
        new_stage: GravityStage,
        forced: bool,
        initiator: str,
    ) -> dict:
        """Execute the promotion."""
        old_stage = node.gravity_stage
        node.gravity_stage = new_stage
        node.promoted = True

        # Mark forced promotion explicitly
        if forced:
            node.forced_promotion = True
            node.forced_by = initiator
            session.add_event(
                "promotion_forced",
                f"Promotion FORCED by {initiator}: {node.title} {old_stage.value} -> {new_stage.value}",
                seat=initiator,
            )
        else:
            session.add_event(
                "promotion_approved",
                f"Promotion approved: {node.title} {old_stage.value} -> {new_stage.value}",
                seat=initiator,
            )

        return {
            "outcome": "promote_now",
            "old_stage": old_stage.value,
            "new_stage": new_stage.value,
            "forced": forced,
            "initiator": initiator,
        }

    def initiate_promotion_vote(
        self,
        session: Session,
        node_id: str,
        seat: str,
        justification: str = "",
        forced: bool = False,
    ) -> dict:
        """Initiate a promotion vote (can be called by user or seat)."""
        node = session.nodes.get(node_id)
        if not node:
            return {"success": False, "reason": "node_not_found"}

        # Store justification if provided
        if justification:
            node.promotion_justification = justification

        # Delegate to vote_on_promotion
        return self.vote_on_promotion(session, node_id, seat, forced=forced)
