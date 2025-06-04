# stratagems.py
import random

# Stratagem Definitions
# W = Up (↑), A = Left (←), S = Down (↓), D = Right (→)
STRATAGEM_LIST = [
    # Offensive - Orbital
    {'name': 'Orbital Gatling Barrage', 'sequence_keys': ['D', 'S', 'A', 'W', 'S'], 'display': "→ ↓ ← ↑ ↓"},
    {'name': 'Orbital Walking Barrage', 'sequence_keys': ['D', 'S', 'D', 'S', 'D', 'S'], 'display': "→ ↓ → ↓ → ↓"},
    {'name': 'Orbital 120MM HE Barrage', 'sequence_keys': ['D', 'S', 'S', 'A', 'S', 'D', 'S', 'S'], 'display': "→ ↓ ↓ ← ↓ → ↓ ↓"},
    {'name': 'Orbital 380MM HE Barrage', 'sequence_keys': ['D', 'S', 'W', 'W', 'A', 'S', 'S'], 'display': "→ ↓ ↑ ↑ ← ↓ ↓"},
    {'name': 'Orbital Gas Strike', 'sequence_keys': ['D', 'D', 'S', 'A', 'W'], 'display': "→ → ↓ ← ↑"},
    {'name': 'Orbital EMS Strike', 'sequence_keys': ['D', 'D', 'A', 'S', 'W'], 'display': "→ → ← ↓ ↑"},
    {'name': 'Orbital Smoke Strike', 'sequence_keys': ['D', 'D', 'S', 'W'], 'display': "→ → ↓ ↑"},
    {'name': 'Orbital Precision Strike', 'sequence_keys': ['D', 'D', 'W'], 'display': "→ → ↑"},
    {'name': 'Orbital Railcannon Strike', 'sequence_keys': ['D', 'W', 'S', 'D', 'A'], 'display': "→ ↑ ↓ → ←"},
    {'name': 'Orbital Laser', 'sequence_keys': ['D', 'S', 'W', 'D', 'S'], 'display': "→ ↓ ↑ → ↓"},

    # Offensive - Eagle
    {'name': 'Eagle Strafing Run', 'sequence_keys': ['W', 'D', 'D'], 'display': "↑ → →"},
    {'name': 'Eagle Napalm Airstrike', 'sequence_keys': ['W', 'D', 'S', 'W', 'D'], 'display': "↑ → ↓ ↑ →"},
    {'name': 'Eagle 110MM Rocket Pods', 'sequence_keys': ['W', 'D', 'W', 'A'], 'display': "↑ → ↑ ←"},
    {'name': 'Eagle Airstrike', 'sequence_keys': ['W', 'D', 'S', 'D'], 'display': "↑ → ↓ →"},
    {'name': 'Eagle Cluster Bomb', 'sequence_keys': ['W', 'D', 'S', 'S', 'D'], 'display': "↑ → ↓ ↓ →"},
    {'name': 'Eagle 500KG Bomb', 'sequence_keys': ['W', 'D', 'S', 'S', 'S'], 'display': "↑ → ↓ ↓ ↓"},

    # Supply & Support
    {'name': 'SOS Beacon', 'sequence_keys': ['W', 'S', 'D', 'W'], 'display': "↑ ↓ → ↑"},
    {'name': 'Resupply', 'sequence_keys': ['S', 'S', 'W', 'D'], 'display': "↓ ↓ ↑ →"},
    {'name': 'Reinforce', 'sequence_keys': ['W', 'S', 'D', 'A', 'W'], 'display': "↑ ↓ → ← ↑"}, # Common one
    {'name': 'Patriot Exosuit', 'sequence_keys': ['A', 'S', 'D', 'W', 'A', 'S', 'S'], 'display': "← ↓ → ↑ ← ↓ ↓"},
    {'name': 'Grenade Launcher', 'sequence_keys': ['S', 'A', 'W', 'A', 'S'], 'display': "↓ ← ↑ ← ↓"},
    {'name': 'Expendable Anti-Tank', 'sequence_keys': ['S', 'S', 'A', 'W', 'D'], 'display': "↓ ↓ ← ↑ →"},
    {'name': 'Railgun', 'sequence_keys': ['S', 'D', 'S', 'W', 'A', 'D'], 'display': "↓ → ↓ ↑ ← →"},
    {'name': 'Autocannon', 'sequence_keys': ['S', 'A', 'S', 'W', 'W', 'D'], 'display': "↓ ← ↓ ↑ ↑ →"},
    {'name': 'Anti-Materiel Rifle', 'sequence_keys': ['S', 'A', 'D', 'W', 'S'], 'display': "↓ ← → ↑ ↓"},
    {'name': 'Machine Gun', 'sequence_keys': ['S', 'A', 'S', 'W', 'A'], 'display': "↓ ← ↓ ↑ ←"},
    {'name': 'Stalwart', 'sequence_keys': ['S', 'A', 'S', 'W', 'W', 'A'], 'display': "↓ ← ↓ ↑ ↑ ←"},

    # Defensive
    {'name': 'Machine Gun Sentry', 'sequence_keys': ['S', 'W', 'D', 'D', 'W'], 'display': "↓ ↑ → → ↑"},
    {'name': 'Gatling Sentry', 'sequence_keys': ['S', 'W', 'D', 'A'], 'display': "↓ ↑ → ←"},
    {'name': 'Autocannon Sentry', 'sequence_keys': ['S', 'W', 'D', 'W', 'A', 'S'], 'display': "↓ ↑ → ↑ ← ↓"},
    {'name': 'Mortar Sentry', 'sequence_keys': ['S', 'W', 'D', 'D', 'S'], 'display': "↓ ↑ → → ↓"},
    {'name': 'Shield Generator Relay', 'sequence_keys': ['S', 'S', 'A', 'D', 'A', 'S'], 'display': "↓ ↓ ← → ← ↓"},
    {'name': 'Anti-Personnel Minefield', 'sequence_keys': ['A', 'S', 'W', 'D'], 'display': "← ↓ ↑ →"}, # Corrected sequence slightly for variety
]

KEY_MAP = {
    'W': 'UP',
    'A': 'LEFT',
    'S': 'DOWN',
    'D': 'RIGHT'
}

def get_stratagem_time_limit(sequence_keys):
    """
    Calculates the time limit based on sequence length (complexity).
    Minimum 5 seconds, maximum 10 seconds.
    Base time 4 seconds + 1 second per key.
    """
    length = len(sequence_keys)
    time = 4 + length 
    return max(5, min(10, time))

# Fallback in case the list is accidentally empty during development
if not STRATAGEM_LIST:
    STRATAGEM_LIST = [
        {"name": "Fallback Reinforce", "sequence_keys": ['W', 'S', 'D', 'D', 'A'], "display": "↑ ↓ → → ←"},
        {"name": "Fallback Resupply", "sequence_keys": ['S', 'S', 'W', 'D'], "display": "↓ ↓ ↑ →"},
    ]