"""Revert-on-no-confirmation behaviour (v1.3.0+).

Regression for the "boiler turns itself off after 5 seconds" bug: an
integration that confirms a command by writing the *same* state again (ZHA
switches, non-dimmable lights, anything whose attributes do not change) makes
Home Assistant fire ``state_reported`` instead of ``state_changed``.  v1.3.0
only listened to ``state_changed``, so it never saw the confirmation and put
the previous state back after the revert timeout, even though the device had
executed the command.
"""
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.optimistic_feedback.const import (
    CONF_DOMAINS,
    CONF_INCLUDE_MODE,
    CONF_REVERT_TIMEOUT,
    CONF_SELECTED_ENTITIES,
    DOMAIN,
)

ENTITY = "switch.boiler"
ATTRS = {"friendly_name": "דוד", "icon": "mdi:water-boiler"}
REVERT_S = 5


async def _setup(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_DOMAINS: ["switch"],
            CONF_INCLUDE_MODE: False,
            CONF_SELECTED_ENTITIES: [],
            CONF_REVERT_TIMEOUT: REVERT_S,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _turn_on(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ENTITY}, blocking=True
    )
    await hass.async_block_till_done()


async def _pass_revert_timeout(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=REVERT_S + 1))
    await hass.async_block_till_done()


async def test_same_state_rewrite_is_a_confirmation(hass: HomeAssistant) -> None:
    """Device answers by re-writing the already-echoed state: must NOT revert."""
    hass.states.async_set(ENTITY, "off", ATTRS)

    async def turn_on(call):
        # What ZHA's switch does after the Zigbee command succeeds: write "on"
        # with unchanged attributes.  The echo already put "on" there, so HA
        # fires state_reported, not state_changed.
        hass.states.async_set(ENTITY, "on", ATTRS, context=call.context)

    hass.services.async_register("switch", "turn_on", turn_on)
    await _setup(hass)

    await _turn_on(hass)
    assert hass.states.get(ENTITY).state == "on"

    await _pass_revert_timeout(hass)
    assert hass.states.get(ENTITY).state == "on", "confirmed command was reverted"


async def test_unconfirmed_command_is_reverted(hass: HomeAssistant) -> None:
    """Device never answers: the previous state comes back after the timeout."""
    hass.states.async_set(ENTITY, "off", ATTRS)

    async def turn_on(call):
        return None  # command swallowed, no state write at all

    hass.services.async_register("switch", "turn_on", turn_on)
    await _setup(hass)

    await _turn_on(hass)
    assert hass.states.get(ENTITY).state == "on"

    await _pass_revert_timeout(hass)
    assert hass.states.get(ENTITY).state == "off"


async def test_changed_attributes_still_confirm(hass: HomeAssistant) -> None:
    """Device answers with a real state_changed (attributes differ): no revert."""
    hass.states.async_set(ENTITY, "off", ATTRS)

    async def turn_on(call):
        hass.states.async_set(ENTITY, "on", {**ATTRS, "power": 2500}, context=call.context)

    hass.services.async_register("switch", "turn_on", turn_on)
    await _setup(hass)

    await _turn_on(hass)
    await _pass_revert_timeout(hass)
    assert hass.states.get(ENTITY).state == "on"
