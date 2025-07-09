"""Optimistic Feedback – instant UI echo for Home Assistant.

Injects an optimistic `state_changed` event the moment a user fires a service
call.  The real device update will overwrite the optimistic one, so the UI
self-repairs if the command fails.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import StateType

from .const import (
    DOMAIN,
    CONF_DOMAINS,
    CONF_EXCLUDE,
    CONF_INCLUDE_MODE,
    CONF_SELECTED_ENTITIES,
    CONF_DEBOUNCE_TIME,
    DEFAULT_DEBOUNCE_MS,
    EVENT_CALL_SERVICE,
)
from .helpers import (
    derive_state, 
    resolve_toggle_state,
    should_apply_optimistic_update,
    record_optimistic_state,
    clear_optimistic_state,
    cleanup_old_optimistic_states,
    set_debounce_time,
)

_LOGGER = logging.getLogger(__name__)

# No platforms (sensors, switches, etc.) – this integration is event-only.
PLATFORMS: list[str] = []

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


# ---------------------------------------------------------------------------
# Home Assistant setup hooks
# ---------------------------------------------------------------------------
async def async_setup(hass: HomeAssistant, _: dict[str, Any]) -> bool:
    """Nothing to do when configured via YAML."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create the event-bus listener according to user options."""
    _LOGGER.info("Setting up Optimistic Feedback integration")
    
    target_domains: set[str] = set(entry.options.get(CONF_DOMAINS, []))
    include_mode: bool = entry.options.get(CONF_INCLUDE_MODE, False)
    selected_entities: set[str] = set(entry.options.get(CONF_SELECTED_ENTITIES, []))
    debounce_time_ms: int = entry.options.get(CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_MS)
    
    # Configure debounce time
    set_debounce_time(debounce_time_ms)
    
    _LOGGER.debug(
        "Configuration: domains=%s, include_mode=%s, selected_entities=%s, debounce=%dms",
        target_domains, include_mode, len(selected_entities), debounce_time_ms
    )
    
    # Legacy support for old exclude format
    excluded_entities: set[str] = set()
    if CONF_EXCLUDE in entry.options:
        excluded_entities = {
            e.strip() for e in entry.options.get(CONF_EXCLUDE, "").split(",") if e.strip()
        }
        _LOGGER.debug("Legacy exclude entities: %s", excluded_entities)

    # -----------------------------------------------------------------------
    # Main handler – inject optimistic state with improved race condition handling
    # -----------------------------------------------------------------------
    @callback
    def _optimistic_echo(event: Event) -> None:
        try:
            data = event.data

            # Only act on selected domains (light, switch, cover, fan …)
            if data["domain"] not in target_domains:
                return

            _LOGGER.debug(
                "Processing service call: domain=%s, service=%s", 
                data["domain"], data["service"]
            )

            # Generate a unique ID for this service call
            service_call_id = f"{data['domain']}.{data['service']}.{datetime.utcnow().timestamp()}"

            optimistic_state, needs_current_state = derive_state(
                hass, data["domain"], data["service"], data.get("service_data", {})
            )
            
            ent_ids = data["service_data"].get(ATTR_ENTITY_ID)
            if not ent_ids:
                _LOGGER.debug("Service call has no target entity_id")
                return  # Service without target entity_id

            # Accept both list and comma-separated string formats
            if isinstance(ent_ids, str):
                ent_ids = [ent_ids]
            
            # Skip multi-entity toggles - too complex for optimistic updates
            if needs_current_state and len(ent_ids) > 1:
                _LOGGER.debug("Skipping multi-entity toggle")
                return

            for ent_id in ent_ids:
                # Apply entity filtering based on include/exclude mode
                if include_mode:
                    # Include mode: only process selected entities
                    if selected_entities and ent_id not in selected_entities:
                        _LOGGER.debug("Entity %s not in include list, skipping", ent_id)
                        continue
                else:
                    # Exclude mode: skip selected entities or legacy excluded entities
                    if ent_id in selected_entities or ent_id in excluded_entities:
                        _LOGGER.debug("Entity %s in exclude list, skipping", ent_id)
                        continue

                # Handle toggle services specially
                if needs_current_state:
                    final_state = resolve_toggle_state(hass, ent_id, data["domain"])
                    if final_state is None:
                        _LOGGER.debug("Could not resolve toggle state for %s", ent_id)
                        continue
                else:
                    final_state = optimistic_state
                    if final_state is None:
                        _LOGGER.debug("No optimistic state derived for %s.%s", data["domain"], data["service"])
                        continue

                # Check if we should apply this optimistic update
                if not should_apply_optimistic_update(ent_id, final_state, service_call_id):
                    continue

                # Apply optimistic state
                old_state = hass.states.get(ent_id)
                attrs = old_state.attributes if old_state else {}
                
                _LOGGER.debug(
                    "Setting optimistic state for %s: %s -> %s", 
                    ent_id, old_state.state if old_state else "unknown", final_state
                )
                
                hass.states.async_set(ent_id, final_state, attrs, force_update=True)
                
                # Record the optimistic state
                record_optimistic_state(ent_id, final_state, service_call_id)
                
        except Exception as e:
            _LOGGER.error("Error in optimistic echo handler: %s", e, exc_info=True)

    # -----------------------------------------------------------------------
    # State change listener to clean up optimistic states when real states arrive
    # -----------------------------------------------------------------------
    @callback
    def _on_state_changed(event: Event) -> None:
        """Clear optimistic state tracking when real state changes arrive."""
        try:
            if event.data.get("entity_id"):
                clear_optimistic_state(event.data["entity_id"])
        except Exception as e:
            _LOGGER.error("Error in state changed handler: %s", e, exc_info=True)

    # -----------------------------------------------------------------------
    # Periodic cleanup
    # -----------------------------------------------------------------------
    async def _periodic_cleanup(now):
        """Periodically clean up old optimistic states."""
        cleanup_old_optimistic_states()

    # Register listeners and cleanup
    remove_service_listener = hass.bus.async_listen(EVENT_CALL_SERVICE, _optimistic_echo)
    remove_state_listener = hass.bus.async_listen("state_changed", _on_state_changed)
    
    # Schedule periodic cleanup every 30 seconds
    cleanup_cancel = async_track_time_interval(
        hass, _periodic_cleanup, timedelta(seconds=30)
    )
    
    entry.async_on_unload(remove_service_listener)
    entry.async_on_unload(remove_state_listener)
    entry.async_on_unload(cleanup_cancel)
    
    _LOGGER.info("Optimistic Feedback integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Detach listener cleanly if the integration is removed."""
    return True  # Nothing else to unload