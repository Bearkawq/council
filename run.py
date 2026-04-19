from __future__ import annotations
import argparse
import json
from engine.engine import CouncilEngine
from core.enums import ViewMode


def print_tree(session, indent=0, node_id=None):
    from core.enums import NodeStatus

    if node_id is None:
        for nid, node in session.nodes.items():
            if node.parent_id is None:
                node_id = nid
                break
    if not node_id:
        return

    node = session.nodes[node_id]
    status_icon = {
        "active": "○",
        "contested": "◐",
        "resolved": "●",
        "blocked": "▣",
        "dead": "✗",
    }.get(node.status.value, "?")

    print(
        "  " * indent
        + f"{status_icon} [{node.gravity_stage.value[:3].upper()}] {node.title[:50]}"
    )
    for child_id in node.children:
        print_tree(session, indent + 1, child_id)


def run_council(topic: str, mode: str = "council", steps: int = 50):
    engine = CouncilEngine()
    view_mode = ViewMode(mode) if mode != "idea" else ViewMode.IDEA
    session = engine.create_session(topic, max_steps=steps, mode=view_mode)

    artifact = engine.run(session)

    print(f"\n{'=' * 60}")
    print(f"COUNCIL SESSION: {topic}")
    print(f"Mode: {mode}, Steps: {session.step_count}")
    print(f"{'=' * 60}")

    print("\n--- Discussion Tree ---")
    print_tree(session)

    print("\n--- Final Artifact ---")
    print(f"Root resolution: {artifact.root_resolution}")
    print(f"Consensus points: {len(artifact.consensus_points)}")
    print(f"Minority objections: {len(artifact.minority_objections)}")
    print(f"Unresolved branches: {len(artifact.unresolved_branches)}")
    print(f"Gravity stages: {artifact.gravity_stage_counts}")
    print(f"Promotions: {len(artifact.promotions)}")
    print(f"Rejected promotions: {len(artifact.rejected_promotions)}")

    if mode == "idea":
        print("\n--- Idea Artifacts ---")
        print(f"Best raw ideas: {len(artifact.keep)}")
        print(f"Best mashups: {len(artifact.keep)}")
        print(f"Best salvage: {len(artifact.keep)}")
        print(f"Best experiments: {len(artifact.keep)}")

    return artifact


def main():
    parser = argparse.ArgumentParser(
        description="Council - structured multi-seat discussion"
    )
    parser.add_argument(
        "topic", nargs="?", default="How should we improve system reliability?"
    )
    parser.add_argument(
        "--mode",
        choices=["council", "duel", "challenge", "stress", "idea"],
        default="council",
    )
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    engine = CouncilEngine()
    view_mode = ViewMode(args.mode) if args.mode != "idea" else ViewMode.IDEA
    session = engine.create_session(args.topic, max_steps=args.steps, mode=view_mode)
    artifact = engine.run(session)

    if args.json:
        result = {
            "topic": args.topic,
            "mode": args.mode,
            "steps": session.step_count,
            "root_resolution": artifact.root_resolution.value
            if artifact.root_resolution
            else None,
            "consensus_count": len(artifact.consensus_points),
            "minority_count": len(artifact.minority_objections),
            "unresolved_count": len(artifact.unresolved_branches),
            "gravity_stages": artifact.gravity_stage_counts,
            "promotions": artifact.promotions,
            "rejected_promotions": artifact.rejected_promotions,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print(f"COUNCIL: {args.topic}")
        print(f"Mode: {args.mode}, Steps: {session.step_count}")
        print(f"{'=' * 60}")
        print("\n--- Tree ---")
        print_tree(session)
        print("\n--- Result ---")
        print(f"Resolution: {artifact.root_resolution}")
        print(
            f"Consensus: {len(artifact.consensus_points)}, Minorities: {len(artifact.minority_objections)}, Unresolved: {len(artifact.unresolved_branches)}"
        )
        print(f"Gravity: {artifact.gravity_stage_counts}")


if __name__ == "__main__":
    main()
