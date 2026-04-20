#!/usr/bin/env python3
"""Council GUI - local web interface."""

from flask import Flask, render_template_string, request, jsonify
from engine.engine import CouncilEngine
from core.enums import ViewMode, GravityStage

app = Flask(__name__)
RUNTIME_MODE = "hybrid"  # simulation, local_llm, hybrid
engine = CouncilEngine(runtime_mode=RUNTIME_MODE)
session = None
selected_branch = None
seat_telemetry = {}


def init_session(topic="Council", mode=ViewMode.COUNCIL):
    global session, selected_branch, seat_telemetry
    session = engine.create_session(topic, mode=mode)
    selected_branch = session.active_queue[0] if session.active_queue else None
    seat_telemetry = {
        seat: {"status": "idle", "model": "", "latency": 0, "error": ""}
        for seat in engine.seat_profiles.keys()
    }


def update_seat_telemetry(
    seat_id: str, status: str, model: str = "", latency: int = 0, error: str = "",
    fallback_used: bool = False, fallback_reason: str = "", failure_class: str = "", action_count: int = 0
):
    seat_telemetry[seat_id] = {
        "status": status,
        "model": model,
        "latency": latency,
        "error": error,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "failure_class": failure_class,
        "action_count": action_count,
    }


HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>COUNCIL</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&family=Playfair+Display:wght@400;600;700&display=swap');
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        :root {
            --bg: #0a0a0b;
            --surface: #111113;
            --surface-2: #18181b;
            --border: #27272a;
            --text: #e4e4e7;
            --text-dim: #71717a;
            --accent: #fafafa;
            --danger: #ef4444;
            --warn: #f59e0b;
            --success: #22c55e;
            --info: #3b82f6;
            --stage-exp: #6b7280;
            --stage-adv: #3b82f6;
            --stage-form: #8b5cf6;
            --stage-trib: #f59e0b;
        }
        
        body {
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: grid;
            grid-template-columns: 1fr 320px;
            grid-template-rows: auto 1fr;
        }
        
        header {
            grid-column: 1 / -1;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
            padding: 10px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        h1 {
            font-family: 'Playfair Display', serif;
            font-size: 1.4rem;
            font-weight: 600;
            letter-spacing: 0.05em;
        }
        
        .status-bar {
            display: flex;
            gap: 20px;
            font-size: 0.7rem;
            color: var(--text-dim);
        }
        
        .mode-toggle {
            display: flex;
            gap: 4px;
        }
        
        .mode-btn {
            background: var(--surface-2);
            border: 1px solid var(--border);
            color: var(--text-dim);
            padding: 4px 12px;
            font-family: inherit;
            font-size: 0.65rem;
            cursor: pointer;
        }
        
        .mode-btn.active {
            background: var(--accent);
            color: var(--bg);
        }
        
        .stage-badge {
            padding: 2px 8px;
            border-radius: 2px;
            font-size: 0.6rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }
        
        .stage-exploratory { background: var(--stage-exp); color: #000; }
        .stage-advisory { background: var(--stage-adv); color: #fff; }
        .stage-formal { background: var(--stage-form); color: #fff; }
        .stage-tribunal { background: var(--stage-trib); color: #000; }
        
        main {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            grid-template-rows: 1fr 1fr;
            gap: 1px;
            background: var(--border);
        }
        
        .panel {
            background: var(--bg);
            padding: 12px;
            overflow: auto;
        }
        
        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 6px;
            border-bottom: 1px solid var(--border);
        }
        
        .panel-title {
            font-size: 0.65rem;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            color: var(--text-dim);
        }
        
        .branch-item {
            padding: 8px 10px;
            margin-bottom: 3px;
            background: var(--surface);
            border-left: 2px solid var(--border);
            font-size: 0.75rem;
            cursor: pointer;
        }
        
        .branch-item:hover { border-left-color: var(--text-dim); }
        .branch-item.active { border-left-color: var(--accent); background: var(--surface-2); }
        
        .branch-meta {
            display: flex;
            gap: 10px;
            margin-top: 3px;
            font-size: 0.6rem;
            color: var(--text-dim);
        }
        
        .contradiction-group {
            margin-bottom: 8px;
        }
        
        .contradiction-header {
            font-size: 0.6rem;
            text-transform: uppercase;
            padding: 2px 6px;
            margin-bottom: 4px;
            display: inline-block;
        }
        
        .contradiction-header.open { background: var(--danger); color: #fff; }
        .contradiction-header.narrowed { background: var(--warn); color: #000; }
        .contradiction-header.merged { background: var(--info); color: #fff; }
        .contradiction-header.resolved { background: var(--success); color: #000; }
        .contradiction-header.unresolved { background: var(--danger); color: #fff; }
        .contradiction-header.deferred { background: var(--text-dim); color: #000; }
        
        .contradiction-item {
            padding: 6px 8px;
            background: var(--surface-2);
            font-size: 0.7rem;
            margin-bottom: 2px;
        }
        
        .action-bar {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }
        
        .action-btn {
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 5px 10px;
            font-family: inherit;
            font-size: 0.6rem;
            cursor: pointer;
        }
        
        .action-btn:hover {
            background: var(--surface-2);
            border-color: var(--text-dim);
        }
        
        .action-btn.danger { border-color: var(--danger); color: var(--danger); }
        .action-btn.danger:hover { background: var(--danger); color: #000; }
        .action-btn.warn { border-color: var(--warn); color: var(--warn); }
        .action-btn.info { border-color: var(--info); color: var(--info); }
        
        .action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        
        .artifact-section {
            padding: 8px;
            background: var(--surface-2);
            margin-bottom: 8px;
            font-size: 0.7rem;
        }
        
        .artifact-header {
            font-size: 0.6rem;
            text-transform: uppercase;
            color: var(--warn);
            margin-bottom: 4px;
        }
        
        .gravity-bar {
            height: 3px;
            background: var(--surface-2);
            margin-top: 3px;
        }
        
        .gravity-fill {
            height: 100%;
            background: var(--accent);
            transition: width 0.3s;
        }
        
        .minority-report {
            background: var(--surface-2);
            border-left: 2px solid var(--warn);
            padding: 6px 8px;
            margin-bottom: 4px;
            font-size: 0.7rem;
        }
        
        .seat-item {
            padding: 8px;
            background: var(--surface-2);
            margin-bottom: 4px;
            font-size: 0.65rem;
        }
        
        .seat-name {
            font-weight: 500;
            margin-bottom: 2px;
        }
        
        .seat-state {
            color: var(--text-dim);
            font-size: 0.6rem;
        }
        
        .seat-telemetry {
            display: flex;
            flex-wrap: wrap;
            gap: 3px;
            margin-top: 4px;
            font-size: 0.5rem;
        }
        
        .telemetry-status {
            padding: 1px 4px;
            border-radius: 2px;
            font-size: 0.45rem;
            text-transform: uppercase;
        }
        .telemetry-status.idle { background: var(--surface); color: var(--text-dim); }
        .telemetry-status.running { background: var(--info); color: #fff; }
        .telemetry-status.success { background: var(--success); color: #000; }
        .telemetry-status.error { background: var(--danger); color: #fff; }
        .telemetry-status.fallback { background: var(--warn); color: #000; }
        
        .telemetry-model {
            background: var(--surface);
            padding: 1px 4px;
            border-radius: 2px;
            font-size: 0.45rem;
        }
        
        .telemetry-latency {
            color: var(--text-dim);
            font-size: 0.45rem;
        }
        
        .telemetry-error {
            color: var(--danger);
            font-size: 0.45rem;
        }
        
        .idea-artifact {
            padding: 6px 8px;
            background: var(--surface);
            margin-bottom: 4px;
            font-size: 0.7rem;
            border-left: 2px solid var(--info);
        }
        
        .candidate-card {
            padding: 6px 8px;
            background: var(--surface-2);
            margin-bottom: 4px;
            font-size: 0.7rem;
            border-left: 2px solid var(--stage-adv);
            display: flex;
            gap: 6px;
        }
        
        .candidate-rank {
            color: var(--text-dim);
            font-size: 0.65rem;
        }
        
        .candidate-status {
            color: var(--text-dim);
            font-size: 0.6rem;
            margin-left: auto;
        }
        
        .panel-subtitle {
            font-size: 0.65rem;
            color: var(--text-dim);
            margin: 8px 0 4px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .narrowing-info {
            font-size: 0.7rem;
            color: var(--warn);
            padding: 4px 8px;
            background: rgba(245, 158, 11, 0.1);
            margin-top: 8px;
        }
        
        .precedent-item {
            padding: 6px 8px;
            background: var(--surface-2);
            margin-bottom: 3px;
            font-size: 0.65rem;
        }
        
        .precedent-item.challenged {
            border-left: 2px solid var(--warn);
        }
        
        aside {
            background: var(--surface);
            border-left: 1px solid var(--border);
            overflow: auto;
        }
        
        .review-item {
            padding: 6px 8px;
            background: var(--surface-2);
            margin-bottom: 4px;
            font-size: 0.7rem;
        }
        
        .forced-badge {
            background: var(--warn);
            color: #000;
            padding: 2px 6px;
            font-size: 0.55rem;
            text-transform: uppercase;
        }
        
        .event-log {
            font-size: 0.6rem;
            color: var(--text-dim);
        }
        
        .event-item {
            padding: 3px 0;
            border-bottom: 1px solid var(--surface-2);
        }
        
        .inspection-meta {
            font-size: 0.65rem;
        }
        
        .inspection-row {
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid var(--surface-2);
        }
        
        .inspection-label { color: var(--text-dim); }
        
        .empty-panel {
            color: var(--text-dim);
            font-size: 0.7rem;
            font-style: italic;
        }
        
        .review-card {
            background: var(--surface-2);
            border: 1px solid var(--border);
            padding: 10px;
            margin-bottom: 8px;
        }
        
        .review-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            padding-bottom: 6px;
            border-bottom: 1px solid var(--border);
        }
        
        .review-type {
            font-size: 0.7rem;
            font-weight: 500;
        }
        
        .review-type.promotion { color: var(--info); }
        .review-type.demotion { color: var(--warn); }
        
        .review-outcome {
            font-size: 0.65rem;
            padding: 3px 8px;
            text-transform: uppercase;
        }
        
        .review-outcome.approved { background: var(--success); color: #000; }
        .review-outcome.deferred { background: var(--warn); color: #000; }
        .review-outcome.rejected { background: var(--danger); color: #fff; }
        .review-outcome.forced { background: var(--warn); color: #000; }
        
        .review-row {
            display: flex;
            justify-content: space-between;
            font-size: 0.65rem;
            padding: 3px 0;
        }
        
        .review-label { color: var(--text-dim); }
        
        .precedent-card {
            background: var(--surface-2);
            border-left: 3px solid var(--info);
            padding: 8px;
            margin-bottom: 6px;
        }
        
        .chamber-status {
            display: flex;
            gap: 4px;
            align-items: center;
        }
        
        .chamber-phase {
            font-size: 0.6rem;
            padding: 2px 8px;
            border-radius: 3px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }
        
        .chamber-phase.deliberation { background: var(--info); color: #fff; }
        .chamber-phase.formal { background: var(--warn); color: #000; }
        .chamber-phase.concluded { background: var(--success); color: #000; }
        
        .action-queue {
            display: flex;
            gap: 4px;
            margin-top: 8px;
        }
        
        .action-pill {
            font-size: 0.55rem;
            padding: 2px 6px;
            background: var(--surface-2);
            border: 1px solid var(--border);
            border-radius: 3px;
        }
        
        .action-pill.active {
            background: var(--accent-dim);
            border-color: var(--accent);
            color: var(--accent);
        }
        
        .precedent-card.challenged { border-left-color: var(--warn); }
        
        .precedent-card.overturned { border-left-color: var(--danger); }
        
        .precedent-outcome {
            font-size: 0.6rem;
            text-transform: uppercase;
            padding: 2px 6px;
            background: var(--surface);
            margin-left: 6px;
        }
        
        .precedent-outcome.upheld { background: var(--success); color: #000; }
        .precedent-outcome.weakened { background: var(--warn); color: #000; }
        .precedent-outcome.overturned { background: var(--danger); color: #fff; }
    </style>
</head>
<body>
    <header>
        <h1>COUNCIL</h1>
        <div class="status-bar">
            <div class="mode-toggle">
                <button class="mode-btn {% if session.mode == 'council' %}active{% endif %}" onclick="doAction('mode council')">COUNCIL</button>
                <button class="mode-btn {% if session.mode == 'open' %}active{% endif %}" onclick="doAction('mode open')">OPEN</button>
                <button class="mode-btn {% if session.mode == 'idea' %}active{% endif %}" onclick="doAction('mode idea')">IDEA</button>
            </div>
            <div class="status-item">
                <span class="status-label">STAGE</span>
                <span class="stage-badge stage-{{ root.gravity_stage.value }}">{{ root.gravity_stage.value[:4] }}</span>
            </div>
            <div class="status-item">
                <span>STEPS: {{ session.step_count }}</span>
            </div>
            <div class="status-item">
                <span>BRANCHES: {{ session.nodes|length }}</span>
            </div>
            {% set promo_count = root.promotion_record|length if root.promotion_record else 0 %}
            {% if promo_count > 0 %}
            <div class="chamber-status">
                <span class="chamber-phase deliberation">PROMO: {{ promo_count }}</span>
                <span class="action-pill active">PROMOTION</span>
            </div>
            {% endif %}
            {% set contrad = session.contradiction_ledger|length %}
            {% if contrad > 0 %}
            <div class="chamber-status">
                <span class="chamber-phase formal">CONTRAD: {{ contrad }}</span>
            </div>
            {% endif %}
        </div>
    </header>
    
    <main>
        <!-- ROW 1 -->
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Active Topic</span>
            </div>
            <div style="font-size: 0.9rem; margin-bottom: 10px;">{{ root.title }}</div>
            <div class="gravity-bar">
                <div class="gravity-fill" style="width: {{ root.gravity * 100 }}%"></div>
            </div>
            <div style="font-size: 0.65rem; color: var(--text-dim); margin-top: 4px;">
                gravity: {{ "%.2f"|format(root.gravity) }}
            </div>
            {% if root.forced_promotion %}
            <div style="margin-top: 8px;">
                <span class="forced-badge">⚠ FORCED by {{ root.forced_by }}</span>
            </div>
            {% endif %}
        </div>
        
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Branches</span>
                <span style="font-size: 0.65rem; color: var(--text-dim);">{{ session.nodes|length }}</span>
            </div>
            {% for node_id, node in session.nodes.items() %}
            <div class="branch-item {% if node_id == selected_branch %}active{% endif %}" onclick="doAction('select {{ node_id }}')">
                <div>{{ node.title[:35] }}</div>
                <div class="branch-meta">
                    <span>S:{{ node.supports|length }}</span>
                    <span>O:{{ node.objections|length }}</span>
                    <span>{{ node.gravity_stage.value[:4] }}</span>
                    <span>⤧{{ node.depth }}</span>
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Branch Inspection</span>
            </div>
            {% if inspection %}
            <div class="inspection-meta">
                <div class="inspection-row">
                    <span class="inspection-label">Title</span>
                    <span>{{ inspection.title[:30] }}</span>
                </div>
                <div class="inspection-row">
                    <span class="inspection-label">Stage</span>
                    <span class="stage-badge stage-{{ inspection.gravity_stage.value }}">{{ inspection.gravity_stage.value }}</span>
                </div>
                <div class="inspection-row">
                    <span class="inspection-label">Gravity</span>
                    <span>{{ "%.2f"|format(inspection.gravity) }}</span>
                </div>
                <div class="inspection-row">
                    <span class="inspection-label">Supports</span>
                    <span>{{ inspection.supports|join(', ') or '-' }}</span>
                </div>
                <div class="inspection-row">
                    <span class="inspection-label">Objections</span>
                    <span>{{ inspection.objections|join(', ') or '-' }}</span>
                </div>
                <div class="inspection-row">
                    <span class="inspection-label">Refinements</span>
                    <span>{{ inspection.refinements|length }}</span>
                </div>
                <div class="inspection-row">
                    <span class="inspection-label">Children</span>
                    <span>{{ inspection.children|length }}</span>
                </div>
            </div>
            {% else %}
            <div class="empty-panel">Select a branch to inspect</div>
            {% endif %}
        </div>
        
        <!-- ROW 2 -->
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Contradictions</span>
                <span style="font-size: 0.65rem; color: var(--text-dim);">{{ session.contradiction_ledger|length }}</span>
            </div>
            {% set status_groups = {} %}
            {% for cid, entry in session.contradiction_ledger.items() %}
                {% set status = entry.status %}
                {% if status not in status_groups %}{% set _ = status_groups.update({status: []}) %}{% endif %}
                {% set _ = status_groups[status].append(entry) %}
            {% endfor %}
            
            {% for status, entries in status_groups.items() %}
            <div class="contradiction-group">
                <span class="contradiction-header {{ status }}">{{ status[:3].upper() }} ({{ entries|length }})</span>
                {% for entry in entries %}
                <div class="contradiction-item">
                    <div style="color: var(--text-dim); font-size: 0.6rem;">{{ entry.source_seat }}</div>
                    <div>{{ entry.summary[:50] }}</div>
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
        
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Actions</span>
            </div>
            <div class="action-bar">
                <button class="action-btn" onclick="doAction('challenge')">challenge</button>
                <button class="action-btn" onclick="doAction('mutate')">mutate</button>
                <button class="action-btn" onclick="doAction('mash')">mash</button>
                <button class="action-btn" onclick="doAction('accept')">accept</button>
                <button class="action-btn" onclick="doAction('pressure')">pressure</button>
            </div>
            <div class="action-bar" style="margin-top: 6px;">
                <button class="action-btn" onclick="doAction('formal')">formal</button>
                <button class="action-btn" onclick="doAction('continue')">continue</button>
            </div>
            
            <!-- PROMOTION/DEMOTION REVIEW CARD -->
            <div class="panel-header" style="margin-top: 10px;">
                <span class="panel-title">Promotion Review</span>
            </div>
            {% set promo_record = root.promotion_record[-1:] if root.promotion_record else [] %}
            {% if promo_record %}
                {% set pr = promo_record[0] %}
                <div class="review-card">
                    <div class="review-header">
                        <span class="review-type promotion">PROMOTION</span>
                        <span class="review-outcome {% if pr.forced %}forced{% endif %}">
                            {% if pr.forced %}FORCED{% else %}{{ last_promo_outcome }}{% endif %}
                        </span>
                    </div>
                    <div class="review-row">
                        <span class="review-label">Initiator</span>
                        <span>{{ pr.seat }}</span>
                    </div>
                    <div class="review-row">
                        <span class="review-label">From</span>
                        <span>{{ pr.from_stage }}</span>
                    </div>
                    <div class="review-row">
                        <span class="review-label">To</span>
                        <span>{{ pr.requested_stage }}</span>
                    </div>
                    {% if pr.forced %}
                    <div class="review-row" style="color: var(--warn);">
                        <span class="review-label">⚠ SCAR</span>
                        <span>FORCED</span>
                    </div>
                    {% endif %}
                </div>
            {% else %}
            <div class="action-bar">
                <button class="action-btn" onclick="doAction('promote')">review</button>
                <button class="action-btn danger" onclick="doAction('promote --force')">FORCE</button>
                <button class="action-btn warn" onclick="doAction('demote')">demote</button>
            </div>
            {% endif %}
            
            <!-- DEMOTION REVIEW CARD -->
            {% set demo_record = root.demotion_history[-1:] if root.demotion_history else [] %}
            {% if demo_record %}
                {% set dr = demo_record[0] %}
                <div class="review-card">
                    <div class="review-header">
                        <span class="review-type demotion">DEMOTION</span>
                        <span class="review-outcome approved">{{ dr.from_stage }} → {{ dr.requested_stage }}</span>
                    </div>
                    <div class="review-row">
                        <span class="review-label">Initiator</span>
                        <span>{{ dr.seat }}</span>
                    </div>
                    <div class="review-row">
                        <span class="review-label">Reason</span>
                        <span>{{ dr.reason[:30] }}</span>
                    </div>
                </div>
            {% endif %}
        </div>
        
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Risk If Ignored</span>
            </div>
            {% if session.risk_if_ignored %}
                {% for risk in session.risk_if_ignored %}
                <div class="artifact-section" style="border-left: 2px solid var(--warn);">
                    {{ risk[:70] }}
                </div>
                {% endfor %}
            {% else %}
            <div class="empty-panel">No active risks</div>
            {% endif %}
        </div>
        
        <!-- ROW 3 -->
        <div class="panel" style="grid-column: 1 / -1;">
            <div class="panel-header">
                <span class="panel-title">Formal Artifact</span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                <div>
                    <div class="artifact-header">Minority Reports</div>
                    {% if session.minority_reports %}
                        {% for node_id, report in session.minority_reports.items() %}
                        <div class="minority-report">{{ report[:80] }}</div>
                        {% endfor %}
                    {% else %}
                    <div class="empty-panel">None</div>
                    {% endif %}
                </div>
                <div>
                    <div class="artifact-header">Contradiction Harvest</div>
                    {% set findings = session.challenge_round_findings %}
                    {% set harvest = findings|select('contains','CONTRADICTION')|list %}
                    {% if harvest %}
                        {% for f in harvest[:3] %}
                        <div class="artifact-section">{{ f[:60] }}</div>
                        {% endfor %}
                    {% else %}
                    <div class="empty-panel">Run formal session</div>
                    {% endif %}
                </div>
                <div>
                    <div class="artifact-header">Final Postures</div>
                    {% if session.opening_statements %}
                        {% for stmt in session.opening_statements[:5] %}
                        <div class="artifact-section">{{ stmt[:50] }}</div>
                        {% endfor %}
                    {% else %}
                    <div class="empty-panel">None</div>
                    {% endif %}
                </div>
            </div>
        </div>
        
        <!-- ROW 4 -->
        <div class="panel" style="grid-column: 1 / 3;">
            <div class="panel-header">
                <span class="panel-title">Event Log</span>
            </div>
            <div class="event-log">
                {% for event in session.replay[-15:] %}
                <div class="event-item">
                    <span>[{{ event.event_type }}]</span>
                    {{ event.detail[:50] }}
                </div>
                {% endfor %}
            </div>
        </div>
        
        <div class="panel" style="grid-column: 3 / -1;">
            <div class="panel-header">
                <span class="panel-title">Seats</span>
                <span style="font-size: 0.5rem; color: var(--text-dim);">{{ runtime_mode }} mode</span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                {% for seat_name, state in session.seat_states.items() %}
                <div class="seat-item">
                    <div class="seat-name">{{ seat_name }}</div>
                    <div class="seat-state">
                        {{ state.direct_challenges }} chal | {{ state.concessions }} con
                    </div>
                    <div class="seat-telemetry">
                        {% if seat_telemetry.get(seat_name) %}
                        <span class="telemetry-status {{ seat_telemetry[seat_name].status }}">{{ seat_telemetry[seat_name].status }}</span>
                        {% if seat_telemetry[seat_name].model %}<span class="telemetry-model">{{ seat_telemetry[seat_name].model }}</span>{% endif %}
                        {% if seat_telemetry[seat_name].latency %}<span class="telemetry-latency">{{ seat_telemetry[seat_name].latency }}ms</span>{% endif %}
                        {% if seat_telemetry[seat_name].get('fallback_used') %}<span class="telemetry-fallback">FALLBACK</span>{% endif %}
                        {% if seat_telemetry[seat_name].get('failure_class') %}<span class="telemetry-error">{{ seat_telemetry[seat_name].failure_class }}</span>{% endif %}
                        {% if seat_telemetry[seat_name].get('action_count', 0) > 1 %}<span class="telemetry-actions">{{ seat_telemetry[seat_name].action_count }}acts</span>{% endif %}
                        {% else %}
                        <span class="telemetry-status idle">idle</span>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </main>
    
    <aside>
        <div class="panel-header">
            <span class="panel-title">Precedents</span>
            <button class="action-btn warn" onclick="doAction('precedent')" style="font-size: 0.55rem; padding: 2px 6px;">+</button>
        </div>
        {% for p in session.precedent_history %}
        <div class="precedent-card {% if p.challenged %}challenged{% endif %}">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="font-weight: 500;">{{ p.topic[:20] }}</span>
                {% if p.challenge_outcome %}
                <span class="precedent-outcome {{ p.challenge_outcome }}">{{ p.challenge_outcome[:3].upper() }}</span>
                {% endif %}
            </div>
            <div style="font-size: 0.6rem; color: var(--text-dim);">
                {{ p.gravity_stage }} | {{ p.resolution }}
            </div>
            {% if p.challenged %}
            <div style="font-size: 0.6rem; margin-top: 4px;">
                <span style="color: var(--warn);">⚠ Challenge active</span>
            </div>
            {% endif %}
        </div>
        {% endfor %}
        {% if not session.precedent_history %}
        <div class="empty-panel">No precedents yet</div>
        {% endif %}
        
        <div class="panel-header" style="margin-top: 12px;">
            <span class="panel-title">Challenge</span>
        </div>
        <div class="action-bar">
            <button class="action-btn warn" onclick="doAction('precedent challenge 1 weakened')">uphold</button>
            <button class="action-btn warn" onclick="doAction('precedent challenge 1 weakened')">weaken</button>
            <button class="action-btn danger" onclick="doAction('precedent challenge 1 overturned')">overturn</button>
        </div>
        
        <!-- IDEA MODE ARTIFACTS -->
        {% if session.mode == 'idea' %}
        <div class="panel-header" style="margin-top: 12px;">
            <span class="panel-title">Best Raw Ideas</span>
        </div>
        {% for idea in session.idea_artifacts.best_raw_ideas[:5] %}
        <div class="idea-artifact">{{ idea[:50] }}</div>
        {% endfor %}
        
        <div class="panel-header">
            <span class="panel-title">Best Mashups</span>
        </div>
        {% for idea in session.idea_artifacts.best_mashups[:5] %}
        <div class="idea-artifact" style="border-left-color: var(--warn);">{{ idea[:50] }}</div>
        {% endfor %}
        
        <div class="panel-header">
            <span class="panel-title">Best Salvage</span>
        </div>
        {% for idea in session.idea_artifacts.best_salvage[:5] %}
        <div class="idea-artifact" style="border-left-color: var(--success);">{{ idea[:50] }}</div>
        {% endfor %}
        
        <div class="panel-header">
            <span class="panel-title">Experiments</span>
        </div>
        {% for idea in session.idea_artifacts.best_experiments[:5] %}
        <div class="idea-artifact" style="border-left-color: var(--stage-form);">{{ idea[:50] }}</div>
        {% endfor %}
        {% endif %}
        
        <!-- OPEN DISCUSSION MODE -->
        {% if session.mode == 'open' and session.open_discussion %}
        <div class="panel-header" style="margin-top: 12px;">
            <span class="panel-title">Open Discussion</span>
        </div>
        
        {% if session.open_discussion.candidate_lines %}
        <div class="panel-subtitle">Candidates</div>
        {% for c in session.open_discussion.candidate_lines[:5] %}
        <div class="candidate-card">
            <span class="candidate-rank">#{{ loop.index }}</span>
            <span class="candidate-title">{{ c.title[:40] }}</span>
            <span class="candidate-status">{{ c.status }}</span>
        </div>
        {% endfor %}
        {% endif %}
        
        {% if session.open_discussion.top_candidates %}
        <div class="panel-subtitle">Top Candidates</div>
        {% for tc in session.open_discussion.top_candidates %}
        <div class="artifact-section" style="border-left-color: var(--success);">
            {{ session.nodes[tc].title[:50] if tc in session.nodes else tc }}
        </div>
        {% endfor %}
        {% endif %}
        
        {% if session.open_discussion.narrowing_round > 0 %}
        <div class="narrowing-info">
            Narrowing: Round {{ session.open_discussion.narrowing_round }}
        </div>
        {% endif %}
        
        {% if session.open_discussion.unresolved_questions %}
        <div class="panel-subtitle">Unresolved</div>
        {% for q in session.open_discussion.unresolved_questions %}
        <div class="artifact-section" style="border-left-color: var(--warn);">
            {{ q[:50] }}
        </div>
        {% endfor %}
        {% endif %}
        
        {% set divergences = [] %}
        {% for sid, snode in session.nodes.items() %}
        {% if snode.objections and snode.objections|length > snode.supports|length %}
        {% set divergences = divergences + [snode.node_id] %}
        {% endif %}
        {% endfor %}
        {% if divergences %}
        <div class="panel-subtitle">Divergence</div>
        {% for did in divergences[:3] %}
        <div class="artifact-section" style="border-left-color: var(--danger);">
            Divergent: {{ session.nodes[did].title[:40] }}
        </div>
        {% endfor %}
        {% endif %}
        {% endif %}
    </aside>
    
    <script>
        async function doAction(cmd) {
            try {
                const resp = await fetch('/action', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({cmd})
                });
                const html = await resp.text();
                document.documentElement.innerHTML = html;
            } catch(e) {
                alert('Error: ' + e);
            }
        }
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    global selected_branch
    if not session:
        init_session()
    if not selected_branch:
        selected_branch = session.active_queue[0] if session.active_queue else None

    root = session.nodes[session.active_queue[0]]
    inspection = session.nodes.get(selected_branch) if selected_branch else root

    return render_template_string(
        HTML,
        session=session,
        root=root,
        selected_branch=selected_branch,
        inspection=inspection,
        runtime_mode=RUNTIME_MODE,
        seat_telemetry=seat_telemetry,
    )


@app.route("/action", methods=["POST"])
def action():
    global session, selected_branch
    if not session:
        return "No session", 500

    data = request.json
    cmd = data.get("cmd", "")
    parts = cmd.split()
    action = parts[0]
    args = parts[1:]

    root = session.nodes[session.active_queue[0]]

    if action == "mode":
        mode_arg = args[0] if args else "council"
        if session.mode != mode_arg:
            session = engine.create_session(session.topic, mode=ViewMode(mode_arg))
            selected_branch = session.active_queue[0]

    elif action == "select":
        node_id = args[0] if args else None
        if node_id and node_id in session.nodes:
            selected_branch = node_id

    elif action == "challenge":
        engine.run_challenge_round(session, root)
    elif action == "mutate":
        engine.mutate_node(session, root)
    elif action == "mash":
        other = list(session.nodes.values())[1] if len(session.nodes) > 1 else root
        engine.mash_nodes(session, root, other)
    elif action == "accept":
        engine.accept_node(session, root)
    elif action == "pressure":
        engine.run_contradiction_pressure(session, root)
    elif action == "continue":
        engine.continue_deliberation(session)
    elif action == "formal":
        engine.run_formal_session(session)

    elif action == "promote":
        forced = "--force" in args
        if forced:
            root.gravity = 0.72
            root.supports = ["Strategist", "Architect"]
            root.risk_if_ignored = ["test risk"]
            root.refinements = ["refined"]
            engine.vote_on_promotion(session, root.node_id, "USER", forced=True)
        else:
            root.gravity = 0.72
            root.supports = ["Strategist"]
            root.risk_if_ignored = ["risk"]
            root.refinements = ["refined"]
            result = engine.vote_on_promotion(session, root.node_id, "USER")
            if result.get("outcome") == "eligible_defer":
                engine.vote_on_promotion(session, root.node_id, "Architect")
                engine.vote_on_promotion(session, root.node_id, "Skeptic")

    elif action == "demote":
        result = engine.vote_on_demotion(session, root.node_id, "USER", "weakened")
        if result.get("outcome") == "demotion_defer":
            engine.vote_on_demotion(session, root.node_id, "Strategist", "weakened")
            engine.vote_on_demotion(session, root.node_id, "Architect", "weakened")

    elif action == "precedent":
        if not session.precedent_history:
            c = type(
                "P",
                (),
                {
                    "topic": root.title[:30],
                    "gravity_stage": str(root.gravity_stage.value),
                    "resolution": "accepted",
                    "challenged": False,
                },
            )
            session.precedent_history.append(c)

    root = session.nodes[session.active_queue[0]]
    inspection = session.nodes.get(selected_branch) if selected_branch else root

    return render_template_string(
        HTML,
        session=session,
        root=root,
        selected_branch=selected_branch,
        inspection=inspection,
    )


def run(port=5123):
    init_session()
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    run()
