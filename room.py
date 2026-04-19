#!/usr/bin/env python3
"""Interactive Council room - live deliberation chamber."""

from __future__ import annotations
import sys
import json
from engine.engine import CouncilEngine
from core.enums import ViewMode, NodeType
from core.models import Node, Precedent


class CouncilRoom:
    def __init__(self, topic: str, mode: str = "council"):
        self.engine = CouncilEngine()
        self.session = self.engine.create_session(topic, mode=ViewMode(mode))
        self.running = True

    def show_status(self):
        """Show current chamber status."""
        root = self.engine.get_root(self.session)

        print(f"\n{'=' * 60}")
        print(f"COUNCIL CHAMBER: {self.session.topic}")
        print(f"Mode: {self.session.mode}, Steps: {self.session.step_count}")
        print(f"{'=' * 60}")

        print(f"\n--- Current Topic ---")
        print(f"[{root.gravity_stage.value[:4].upper()}] {root.title}")

        print(f"\n--- Branch Status ---")
        for node_id, node in self.session.nodes.items():
            if node.parent_id:
                status = "○" if node.status.value == "active" else "●"
                supports = len(node.supports)
                objections = len(node.objections)
                print(f"  {status} {node.title[:40]} (S:{supports} O:{objections})")

        print(f"\n--- Minority Objections ---")
        minority = [
            n
            for n in self.session.nodes.values()
            if len(n.objections) > len(n.supports)
        ]
        if minority:
            for n in minority[:3]:
                print(f"  ⚠ {n.title[:50]}")
        else:
            print("  (none)")

        if self.session.minority_reports:
            print(f"\n--- Minority Reports ---")
            for node_id, report in list(self.session.minority_reports.items())[:2]:
                print(f"  {report[:60]}")

        if self.session.risk_if_ignored:
            print(f"\n--- Risk If Ignored ---")
            for risk in self.session.risk_if_ignored[:2]:
                print(f"  ⚡ {risk[:60]}")

    def run_command(self, cmd: str, args: list) -> bool:
        """Execute a room command."""
        if cmd in ("quit", "exit", "q"):
            self.running = False
            print("Exiting chamber.")
            return True

        elif cmd in ("help", "?"):
            self._show_help()
            return True

        elif cmd == "status":
            self.show_status()
            return True

        elif cmd == "challenge":
            return self._cmd_challenge(args)

        elif cmd == "mutate":
            return self._cmd_mutate(args)

        elif cmd == "mash":
            return self._cmd_mash(args)

        elif cmd == "accept":
            return self._cmd_accept(args)

        elif cmd == "pressure":
            return self._cmd_pressure(args)

        elif cmd == "continue":
            return self._cmd_continue(args)

        elif cmd == "formal":
            return self._cmd_formal(args)

        elif cmd == "precedent":
            return self._cmd_precedent(args)

        elif cmd == "promote":
            return self._cmd_promote(args)

        elif cmd == "demote":
            return self._cmd_demote(args)

        elif cmd == "tree":
            self._show_tree()
            return True

        else:
            print(f"Unknown command: {cmd}")
            self._show_help()
            return True

    def _show_help(self):
        print("""
 COUNCIL CHAMBER COMMANDS:
   status      - Show current chamber status
   tree        - Show discussion tree
   challenge   - Challenge a seat's position
   mutate      - Mutate a branch
   mash        - Mash two branches together
   accept      - Accept a branch as resolution
   pressure    - Pressure test a branch
   continue    - Continue deliberation
   formal      - Run formal session
   precedent   - Show/cite past precedents
   promote     - Initiate promotion vote
   demote      - Vote on demotion
   quit        - Exit chamber
 """)

    def _cmd_challenge(self, args: list) -> bool:
        """Challenge a seat's position on a node."""
        if not args:
            print("Usage: challenge <seat> <node_id>")
            return True

        seat = args[0]
        node_id = args[1] if len(args) > 1 else None

        if not node_id:
            # Default to root
            node_id = list(self.session.nodes.keys())[0]

        node = self.session.nodes.get(node_id)
        if not node:
            print(f"Node not found: {node_id}")
            return True

        # Add objection from user (as special seat)
        node.objections.append("USER")
        self.session.add_event(
            "user_challenge",
            f"User challenged {seat} on {node.title}",
            seat="USER",
            node_id=node_id,
        )
        print(f"✓ Challenged {seat} on: {node.title}")

        # Trigger seat reaction
        self._trigger_seat_reaction(seat, node, "challenge")

        return True

    def _trigger_seat_reaction(self, seat: str, node: Node, reaction_type: str):
        """Show rich seat reaction to user action."""
        prev_supports = len(node.supports)
        prev_objections = len(node.objections)

        # Show initial reaction
        reactions = {
            "Strategist": f"[STRATEGIST] A fair challenge. Let me clarify the decision space.",
            "Architect": f"[ARCHITECT] The boundary is worth examining more carefully.",
            "Researcher": f"[RESEARCHER] This raises an important alternative to consider.",
            "Operator": f"[OPERATOR] Practical point. What's the simplest way forward?",
            "Skeptic": f"[SKEPTIC] Interesting. Where's the hidden contradiction?",
        }

        if seat in reactions:
            print(f"  {reactions[seat]}")

        # Update node gravity and show what changed
        node.gravity = min(1.0, node.gravity + 0.1)
        self.engine.update_gravity(node)

        # Show branch status after reaction
        print(f"\n  → Branch status: {node.gravity_stage.value}")
        if node.gravity > 0.6:
            print(f"  → Gravity increased to {node.gravity:.2f} - branch is hardening")
        else:
            print(f"  → Branch remains exploratory")

        # Show what might strengthen/weaken
        if node.support_level > 0.3:
            print(f"  → This branch is gaining support, may strengthen")
        elif len(node.objections) > len(node.supports):
            print(f"  → This branch is weakening under minority objection")

    def _cmd_mutate(self, args: list) -> bool:
        """Mutate a branch with new direction."""
        if not args:
            print("Usage: mutate <parent_id> <new_title>")
            return True

        parent_id = args[0]
        new_title = " ".join(args[1:])

        if not new_title:
            print("Usage: mutate <parent_id> <new_title>")
            return True

        parent = self.session.nodes.get(parent_id)
        if not parent:
            print(f"Parent node not found: {parent_id}")
            return True

        mutation = Node(
            node_id=self.session.next_node_id(),
            node_type=NodeType.TWIST,
            title=f"MUTATION: {new_title}",
            summary=f"User-mutated from {parent.title}",
            parent_id=parent_id,
            created_by="USER",
            depth=parent.depth + 1,
            confidence=0.6,
            gravity=0.45,
        )

        self.session.nodes[mutation.node_id] = mutation
        parent.children.append(mutation.node_id)
        self.session.active_queue.append(mutation.node_id)

        print(f"✓ Created mutation: {mutation.title}")
        return True

    def _cmd_mash(self, args: list) -> bool:
        """Mash two branches together."""
        if len(args) < 2:
            print("Usage: mash <node1_id> <node2_id>")
            return True

        node1 = self.session.nodes.get(args[0])
        node2 = self.session.nodes.get(args[1])

        if not node1 or not node2:
            print(f"Nodes not found")
            return True

        mashup = Node(
            node_id=self.session.next_node_id(),
            node_type=NodeType.MASHUP,
            title=f"MASHUP: {node1.title} + {node2.title[:30]}",
            summary=f"Combined: {node1.summary[:50]} ... {node2.summary[:50]}",
            parent_id=node1.parent_id or node1.node_id,
            created_by="USER",
            depth=max(node1.depth, node2.depth) + 1,
            confidence=0.55,
            gravity=0.5,
        )

        self.session.nodes[mashup.node_id] = mashup
        self.session.active_queue.append(mashup.node_id)

        print(f"✓ Created mashup: {mashup.title}")
        return True

    def _cmd_accept(self, args: list) -> bool:
        """Accept a branch as resolution."""
        if not args:
            print("Usage: accept <node_id>")
            return True

        node = self.session.nodes.get(args[0])
        if not node:
            print(f"Node not found")
            return True

        node.status = self.session.nodes[node.node_id].status = "resolved"
        node.resolution_state = "accepted"

        self.session.add_event(
            "branch_accepted", f"User accepted: {node.title}", node_id=node.node_id
        )

        # Record as precedent
        precedent = Precedent(
            id=f"p{len(self.session.precedent_history) + 1}",
            topic=node.title,
            artifact_summary=node.summary,
            gravity_stage=node.gravity_stage.value,
            resolution="accepted",
        )
        self.session.precedent_history.append(precedent)

        print(f"✓ Accepted: {node.title}")
        return True

    def _cmd_pressure(self, args: list) -> bool:
        """Pressure test a branch."""
        if not args:
            print("Usage: pressure <node_id>")
            return True

        node = self.session.nodes.get(args[0])
        if not node:
            print(f"Node not found")
            return True

        # Apply pressure
        node.gravity = min(1.0, node.gravity + 0.15)

        # Add risk
        risk = (
            f"Risk: {node.title} may be wrong if pressure reveals hidden contradiction"
        )
        node.risk_if_ignored.append(risk)
        self.session.risk_if_ignored.append(risk)

        # Trigger Skeptic
        self.engine.run_contradiction_pressure(self.session, node)

        print(f"✓ Applied pressure to: {node.title}")
        print(f"  Gravity increased to {node.gravity:.2f}")

        return True

    def _cmd_continue(self, args: list) -> bool:
        """Continue normal deliberation."""
        steps = int(args[0]) if args and args[0].isdigit() else 1

        self.session.max_steps = min(self.session.max_steps + steps, 100)
        artifact = self.engine.run(self.session)

        print(f"✓ Ran {steps} more step(s)")
        self.show_status()
        return True

    def _cmd_formal(self, args: list) -> bool:
        """Run formal session."""
        self.session.formal_session = True
        self.engine.run_formal_session(self.session)

        print("✓ Formal session complete:")
        print(f"  Opening statements: {len(self.session.opening_statements)}")
        print(f"  Challenge findings: {len(self.session.challenge_round_findings)}")
        print(f"  Minority reports: {len(self.session.minority_reports)}")

        if self.session.minority_reports:
            print("\n--- Minority Reports ---")
            for node_id, report in self.session.minority_reports.items():
                print(f"  {report[:80]}")

        if self.session.risk_if_ignored:
            print("\n--- Risk If Ignored ---")
            for risk in self.session.risk_if_ignored:
                print(f"  ⚡ {risk[:80]}")

        return True

    def _cmd_promote(self, args: list) -> bool:
        """Initiate promotion vote on a branch."""
        if not args:
            print("Usage: promote <node_id> [justification]")
            print("   Or: promote <node_id> --force [justification]")
            return True

        node_id = args[0]
        force = "--force" in args

        if force:
            args.remove("--force")

        justification = " ".join(args[1:]) if len(args) > 1 else ""

        node = self.session.nodes.get(node_id)
        if not node:
            print(f"Node not found: {node_id}")
            return True

        # Show eligibility check first
        eligibility = self.engine._check_promotion_eligibility(
            self.session, node, "USER"
        )

        print(f"\n--- Promotion Review: {node.title[:40]} ---")
        print(f"Current stage: {node.gravity_stage.value}")

        if not eligibility["eligible"]:
            print(f"❌ NOT ELIGIBLE: {eligibility['reason']}")
            print("  Evidence:")
            for ev in eligibility["evidence"]:
                print(f"    - {ev}")
            return True

        print(f"✓ ELIGIBLE for promotion")
        print("  Evidence:")
        for ev in eligibility["evidence"]:
            print(f"    + {ev}")

        # Execute vote
        result = self.engine.initiate_promotion_vote(
            self.session, node_id, "USER", justification=justification, forced=force
        )

        print(f"\n  Vote outcome: {result.get('outcome', 'unknown')}")

        if result.get("outcome") == "promote_now":
            print(
                f"  ⚡ PROMOTED: {result.get('old_stage')} -> {result.get('new_stage')}"
            )
            if result.get("forced"):
                print(f"  ⚠ FORCED by user (leaves visible scar)")
        elif result.get("outcome") == "eligible_defer":
            print(
                f"  ⏸ Eligible but deferred: {result.get('reason', 'not enough votes')}"
            )
        elif result.get("outcome") == "reject":
            print(f"  ❌ Rejected: {result.get('reason', 'not eligible')}")

        return True

    def _cmd_demote(self, args: list) -> bool:
        """Vote on demoting a branch."""
        if not args:
            print("Usage: demote <node_id> <reason>")
            return True

        node_id = args[0]
        reason = " ".join(args[1:]) if len(args) > 1 else "Branch weakened"

        node = self.session.nodes.get(node_id)
        if not node:
            print(f"Node not found: {node_id}")
            return True

        print(f"\n--- Demotion Review: {node.title[:40]} ---")
        print(f"Current stage: {node.gravity_stage.value}")

        result = self.engine.vote_on_demotion(
            self.session, node_id, "USER", reason=reason
        )

        if result.get("outcome") == "demote_now":
            print(
                f"  ⚡ DEMOTED: {result.get('old_stage')} -> {result.get('new_stage')}"
            )
            print(f"  Demoted by: {result.get('demoted_by')}")
            print(f"  Reason: {result.get('reason')}")
        elif result.get("outcome") == "demotion_defer":
            print(
                f"  ⏸ Demotion deferred: {result.get('votes')}/{result.get('needed')} votes"
            )
        elif result.get("outcome") == "reject":
            print(f"  ❌ Rejected: {result.get('reason')}")

        return True

    def _cmd_precedent(self, args: list) -> bool:
        """Show, cite, or challenge precedents."""
        if not self.session.precedent_history:
            print("No precedents yet. Accept a branch to create one.")
            return True

        if args and args[0] == "cite":
            # Cite a precedent
            idx = int(args[1]) - 1 if len(args) > 1 else 0
            if 0 <= idx < len(self.session.precedent_history):
                p = self.session.precedent_history[idx]
                p.citation_count += 1
                print(
                    f"Citing precedent: {p.topic} ({p.gravity_stage}, {p.resolution})"
                )
            return True

        if args and args[0] == "challenge":
            # Challenge a precedent with outcome
            idx = int(args[1]) - 1 if len(args) > 1 else 0
            outcome = args[2] if len(args) > 2 else "weakened"
            if outcome not in ("upheld", "weakened", "rejected"):
                print("Outcome must be: upheld, weakened, or rejected")
                return True

            if 0 <= idx < len(self.session.precedent_history):
                p = self.session.precedent_history[idx]
                p.challenged = True
                p.challenge_outcome = outcome
                p.citation_count = max(0, p.citation_count - 1)
                print(f"⚠ CHALLENGED precedent: {p.topic}")
                print(f"  Outcome: {outcome.upper()}")
                print(f"  This precedent is now explicitly {outcome}.")
                print(f"  It remains in history but is no longer silently binding.")

                # Add to contradictions as evidence of challenge
                self.session.add_event(
                    "precedent_challenged",
                    f"Precedent {p.topic} challenged -> {outcome}",
                    seat="USER",
                )
            return True

        print("--- Precedent History ---")
        for i, p in enumerate(self.session.precedent_history):
            status = "⚠" if p.challenged else "○"
            print(
                f"  {i + 1}. {status} {p.topic[:35]} | {p.gravity_stage} | {p.resolution} | cited {p.citation_count}x"
            )

        print("\nUse: precedent cite <n>  to cite a precedent")
        print("Use: precedent challenge <n>  to challenge a precedent")

        return True

    def _show_tree(self):
        """Show discussion tree."""
        root = self.engine.get_root(self.session)
        self._print_node_tree(root, 0)

    def _print_node_tree(self, node: Node, indent: int):
        icon = {"active": "○", "resolved": "●", "contested": "◐"}.get(
            node.status.value, "?"
        )
        print(
            "  " * indent
            + f"{icon} [{node.gravity_stage.value[:3].upper()}] {node.title[:50]}"
        )

        for child_id in node.children:
            if child_id in self.session.nodes:
                self._print_node_tree(self.session.nodes[child_id], indent + 1)


def main():
    topic = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "How should we improve system reliability?"
    )
    mode = "council"

    if "--idea" in sys.argv:
        mode = "idea"

    room = CouncilRoom(topic, mode)

    print(f"\nWelcome to Council Chamber: {topic}")
    print("Type 'help' for commands, 'quit' to exit.\n")

    room.show_status()

    while room.running:
        try:
            prompt = f"\n[Council] "
            cmd_line = input(prompt).strip()
            if not cmd_line:
                continue

            parts = cmd_line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            room.run_command(cmd, args)

        except KeyboardInterrupt:
            print("\nExiting chamber.")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
