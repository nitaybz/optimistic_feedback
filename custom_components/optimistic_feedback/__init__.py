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
from homeassistant.core import Context, Event, HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.typing import StateType

from .const import (
    DOMAIN,
    CONF_DOMAINS,
    CONF_EXCLUDE,
    CONF_INCLUDE_MODE,
    CONF_SELECTED_ENTITIES,
    CONF_DEBOUNCE_TIME,
    CONF_REVERT_TIMEOUT,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_REVERT_TIMEOUT_S,
    EVENT_CALL_SERVICE,
)
from .helpers import (
    derive_state, 
    resolve_toggle_state,
    resolve_climate_set_temperature_state,
    should_apply_optimistic_update,
    record_optimistic_state,
    clear_optimistic_state,
    cleanup_old_optimistic_states,
    get_optimistic_state,
    discard_optimistic_state,
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
    revert_timeout_s: float = float(
        entry.options.get(CONF_REVERT_TIMEOUT, DEFAULT_REVERT_TIMEOUT_S)
    )
    
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

                # OFFLINE GUARD (v1.2.2, 2026-06-10): never echo an optimistic
                # state over an entity that is currently unavailable/unknown.
                # Echoing e.g. "on" onto an offline device HIDES the failure — the
                # state would read back the optimistic target indefinitely, so the
                # UI (and any consumer checking state) believes a command that
                # never reached the device succeeded. Leaving the real
                # `unavailable` state in place lets the failure surface honestly.
                existing_state = hass.states.get(ent_id)
                if existing_state is None or existing_state.state in ("unavailable", "unknown"):
                    _LOGGER.debug(
                        "Skipping optimistic echo for %s — current state is %s (treated as offline)",
                        ent_id, existing_state.state if existing_state else "missing",
                    )
                    continue

                # Handle services that require current state analysis
                if needs_current_state:
                    if data["domain"] == "climate" and data["service"] == "set_temperature":
                        # Special handling for climate set_temperature
                        final_state = resolve_climate_set_temperature_state(hass, ent_id, data.get("service_data", {}))
                    else:
                        # Regular toggle logic
                        final_state = resolve_toggle_state(hass, ent_id, data["domain"])
                    
                    if final_state is None:
                        _LOGGER.debug("Could not resolve state for %s", ent_id)
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
                
                # Tag our own write so the state listener can tell this echo
                # apart from a genuine update coming back from the device.
                echo_context = Context()
                hass.states.async_set(
                    ent_id, final_state, attrs, force_update=True, context=echo_context
                )

                # Record the optimistic state, remembering what was there before
                # so it can be restored if the device never confirms.
                record_optimistic_state(
                    ent_id,
                    final_state,
                    service_call_id,
                    context_id=echo_context.id,
                    previous_state=old_state.state if old_state else None,
                    previous_attributes=dict(attrs) if attrs else {},
                )

                if revert_timeout_s > 0:
                    _schedule_revert(ent_id, service_call_id)
                
        except Exception as e:
            _LOGGER.error("Error in optimistic echo handler: %s", e, exc_info=True)

    # -----------------------------------------------------------------------
    # Revert an optimistic state the device never confirmed
    # -----------------------------------------------------------------------
    @callback
    def _revert_if_unconfirmed(entity_id: str, service_call_id: str) -> None:
        """Put the previous state back if the device never answered.

        Without this the UI keeps showing the predicted state forever whenever a
        command does not reach the device, which reports a failed action as a
        success. Only reverts when nothing else has touched the entity since,
        so a real update (or a newer optimistic update) is never overwritten.
        """
        record = get_optimistic_state(entity_id)
        if record is None or record.service_call_id != service_call_id:
            return  # Superseded by a newer optimistic update, or already cleared

        if record.real_state_received:
            discard_optimistic_state(entity_id)
            return  # Device confirmed - nothing to do

        current = hass.states.get(entity_id)
        if current is None:
            discard_optimistic_state(entity_id)
            return

        # Only revert what we ourselves wrote and nobody has changed since.
        if current.context.id != record.context_id:
            discard_optimistic_state(entity_id)
            return

        if record.previous_state is None:
            discard_optimistic_state(entity_id)
            return

        _LOGGER.warning(
            "Reverting optimistic state for %s: %s was not confirmed within %ss, "
            "restoring %s",
            entity_id, record.state, revert_timeout_s, record.previous_state,
        )
        hass.states.async_set(
            entity_id,
            record.previous_state,
            record.previous_attributes or {},
            force_update=True,
        )
        discard_optimistic_state(entity_id)

    @callback
    def _schedule_revert(entity_id: str, service_call_id: str) -> None:
        """Arm the revert check for a single optimistic update."""

        @callback
        def _run(_now) -> None:
            _revert_if_unconfirmed(entity_id, service_call_id)

        async_call_later(hass, revert_timeout_s, _run)

    # -----------------------------------------------------------------------
    # State change listener to clean up optimistic states when real states arrive
    # -----------------------------------------------------------------------
    @callback
    def _on_state_changed(event: Event) -> None:
        """Clear optimistic state tracking when real state changes arrive."""
        try:
            entity_id = event.data.get("entity_id")
            if not entity_id:
                return

            record = get_optimistic_state(entity_id)
            if record is None:
                return

            # Our own optimistic write also raises state_changed. Treating that
            # as the device responding would immediately mark the prediction
            # confirmed and defeat the revert entirely.
            if record.context_id and event.context and event.context.id == record.context_id:
                return

            clear_optimistic_state(entity_id)
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