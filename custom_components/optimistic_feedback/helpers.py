"""Helper utilities for Optimistic Feedback."""

from __future__ import annotations

import logging
from datetime import timedelta, datetime
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from homeassistant.core import HomeAssistant, State

from .const import SERVICE_MAP, DEFAULT_DEBOUNCE_MS

_LOGGER = logging.getLogger(__name__)

@dataclass
class OptimisticState:
    """Track optimistic state information."""
    state: str
    timestamp: datetime
    service_call_id: str  # Track which service call created this
    real_state_received: bool = False

# ---------------------------------------------------------------------------
# Enhanced state tracking
# ---------------------------------------------------------------------------
_OPTIMISTIC_STATES: Dict[str, OptimisticState] = {}
_DEBOUNCE_TIME_MS = DEFAULT_DEBOUNCE_MS

def set_debounce_time(ms: int) -> None:
    """Set the debounce time in milliseconds."""
    global _DEBOUNCE_TIME_MS
    _DEBOUNCE_TIME_MS = max(50, min(2000, ms))  # Clamp between 50ms and 2s
    _LOGGER.debug("Debounce time set to %dms", _DEBOUNCE_TIME_MS)

def get_debounce_time() -> timedelta:
    """Get the current debounce time."""
    return timedelta(milliseconds=_DEBOUNCE_TIME_MS)

def should_apply_optimistic_update(
    entity_id: str, 
    new_state: str,
    service_call_id: str
) -> bool:
    """
    Determine if we should apply an optimistic update.
    
    Returns True if:
    - No recent optimistic state for this entity, OR
    - The new state is different from current optimistic state, OR
    - Enough time has passed since last optimistic update
    """
    now = datetime.utcnow()
    current_optimistic = _OPTIMISTIC_STATES.get(entity_id)
    
    if not current_optimistic:
        return True
    
    # Different state? Always allow
    if current_optimistic.state != new_state:
        return True
    
    # Same state but enough time passed? Allow
    time_diff = now - current_optimistic.timestamp
    if time_diff >= get_debounce_time():
        return True
    
    # Same state, recent update, same service call ID? Skip
    if current_optimistic.service_call_id == service_call_id:
        _LOGGER.debug(
            "Skipping duplicate optimistic update for %s (same service call)", 
            entity_id
        )
        return False
        
    return True

def record_optimistic_state(
    entity_id: str, 
    state: str, 
    service_call_id: str
) -> None:
    """Record that we've applied an optimistic state."""
    _OPTIMISTIC_STATES[entity_id] = OptimisticState(
        state=state,
        timestamp=datetime.utcnow(),
        service_call_id=service_call_id,
        real_state_received=False
    )
    _LOGGER.debug("Recorded optimistic state %s=%s", entity_id, state)

def clear_optimistic_state(entity_id: str) -> None:
    """Clear optimistic state when real state is received."""
    if entity_id in _OPTIMISTIC_STATES:
        _OPTIMISTIC_STATES[entity_id].real_state_received = True
        _LOGGER.debug("Marked real state received for %s", entity_id)

def cleanup_old_optimistic_states() -> None:
    """Clean up old optimistic states that are no longer relevant."""
    now = datetime.utcnow()
    cutoff = timedelta(seconds=30)  # Clean up states older than 30 seconds
    
    to_remove = [
        entity_id for entity_id, opt_state in _OPTIMISTIC_STATES.items()
        if now - opt_state.timestamp > cutoff or opt_state.real_state_received
    ]
    
    for entity_id in to_remove:
        del _OPTIMISTIC_STATES[entity_id]
    
    if to_remove:
        _LOGGER.debug("Cleaned up optimistic states for: %s", to_remove)


# ---------------------------------------------------------------------------
# State-derivation logic
# ---------------------------------------------------------------------------
def derive_state(
    hass: HomeAssistant,
    domain: str,
    service: str,
    service_data: dict,
) -> Tuple[str | None, bool]:
    """
    Return the state string we *predict* will be true after the call.
    
    Returns:
        Tuple of (predicted_state, requires_current_state)
        - predicted_state: The state we predict, or None if unpredictable
        - requires_current_state: True if we need current state for toggle logic
    """
    _LOGGER.debug(
        "Deriving state for domain=%s, service=%s, data=%s", 
        domain, service, service_data
    )
    
    # 1. Domain-specific logic first
    if domain == "cover":
        state, needs_current = _derive_cover_state(service, service_data)
        return state, needs_current
    elif domain == "climate":
        state, needs_current = _derive_climate_state(service, service_data)
        return state, needs_current
    elif domain == "media_player":
        state, needs_current = _derive_media_player_state(service, service_data)
        return state, needs_current
    
    # 2. Toggle requires current state
    if service == "toggle":
        return None, True  # Signal that we need current state
    
    # 3. Straight mapping (turn_on → "on", etc.)
    if service in SERVICE_MAP:
        return SERVICE_MAP[service], False

    # 4. Unknown service – no optimistic echo
    _LOGGER.debug("Unknown service %s for domain %s", service, domain)
    return None, False

def resolve_toggle_state(
    hass: HomeAssistant,
    entity_id: str,
    domain: str
) -> str | None:
    """
    Resolve toggle state by looking at current state.
    This is separate to avoid race conditions.
    """
    # First check if we have a recent optimistic state
    optimistic = _OPTIMISTIC_STATES.get(entity_id)
    if optimistic and not optimistic.real_state_received:
        current_state = optimistic.state
        _LOGGER.debug("Using optimistic state for toggle: %s = %s", entity_id, current_state)
    else:
        # Use real state
        state_obj = hass.states.get(entity_id)
        if not state_obj:
            _LOGGER.debug("No current state found for entity %s", entity_id)
            return None
        current_state = state_obj.state
        _LOGGER.debug("Using real state for toggle: %s = %s", entity_id, current_state)
    
    # Determine new state based on domain and current state
    if domain in ["light", "switch", "fan"]:
        new_state = "off" if current_state == "on" else "on"
    elif domain == "cover":
        new_state = "closed" if current_state in ["open", "opening"] else "open"
    elif domain == "media_player":
        new_state = "paused" if current_state == "playing" else "playing"
    elif domain == "lock":
        new_state = "unlocked" if current_state == "locked" else "locked"
    else:
        # Generic toggle
        new_state = "off" if current_state in ["on", "open", "playing", "locked"] else "on"
    
    _LOGGER.debug("Toggle resolved: %s -> %s", current_state, new_state)
    return new_state


def _derive_cover_state(service: str, service_data: dict) -> Tuple[str | None, bool]:
    """Derive state for cover domain services."""
    if service == "set_cover_position":
        pos = service_data.get("position")
        if pos is None:
            return None, False
        return ("closed" if int(pos) == 0 else "open"), False
    elif service == "set_cover_tilt_position":
        # Tilt doesn't change open/closed state
        return None, False
    elif service == "toggle":
        return None, True  # Needs current state
    
    mapped_state = SERVICE_MAP.get(service)
    return mapped_state, False


def _derive_climate_state(service: str, service_data: dict) -> Tuple[str | None, bool]:
    """Derive state for climate domain services."""
    if service == "set_hvac_mode":
        return service_data.get("hvac_mode"), False
    elif service == "turn_on":
        return "heat", False  # Common default
    elif service == "turn_off":
        return "off", False
    return None, False


def _derive_media_player_state(service: str, service_data: dict) -> Tuple[str | None, bool]:
    """Derive state for media_player domain services."""
    media_service_map = {
        "media_play": "playing",
        "media_pause": "paused", 
        "media_stop": "idle",
        "turn_on": "idle",
        "turn_off": "off",
    }
    if service == "toggle":
        return None, True  # Needs current state
    
    return media_service_map.get(service), False