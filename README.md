# Council

A multi-seat structured deliberation system with gravity stages, promotions, demotions, and contradictions.

## Overview

Council is a local-first deliberation engine that simulates structured multi-seat discussions. Ideas flow through gravity stages from exploratory to formal to tribunal.

## Running

```bash
# CLI
python3 run.py "Your topic here" --steps 10 --mode council

# GUI
python3 gui.py
# Opens at http://127.0.0.1:5000
```

## Modes

- `council` - Full multi-seat deliberation
- `duel` - Two opposing seats
- `challenge` - Adversarial testing
- `stress` - Stress testing
- `idea` - Idea generation/evolution

## Architecture

- `engine/engine.py` - Core deliberation engine
- `core/models.py` - Data models
- `core/enums.py` - Gravity stages, node types
- `seats/seat_profiles.py` - Seat behaviors
- `gui.py` - Flask web interface
- `room.py` - WebSocket room support