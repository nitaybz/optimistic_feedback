"""UI flow: pick target domains & entity inclusion/exclusion."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_DOMAINS, 
    CONF_EXCLUDE, 
    CONF_INCLUDE_MODE,
    CONF_SELECTED_ENTITIES,
    CONF_DEBOUNCE_TIME,
    DEFAULT_DOMAINS, 
    ALL_SUPPORTED_DOMAINS,
    DEFAULT_DEBOUNCE_MS,
    DOMAIN
)


class OptimisticConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _NAME = "Optimistic Feedback"

    async def async_step_user(self, user_input=None):
        """Handle initial setup - only create one entry."""
        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=self._NAME, 
                data={}, 
                options={
                    CONF_DOMAINS: user_input.get(CONF_DOMAINS, DEFAULT_DOMAINS),
                    CONF_INCLUDE_MODE: user_input.get(CONF_INCLUDE_MODE, False),
                    CONF_SELECTED_ENTITIES: user_input.get(CONF_SELECTED_ENTITIES, []),
                    CONF_DEBOUNCE_TIME: user_input.get(CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_MS),
                }
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DOMAINS, default=DEFAULT_DOMAINS): SelectSelector(
                    SelectSelectorConfig(
                        options=ALL_SUPPORTED_DOMAINS,
                        multiple=True,
                        mode="dropdown",
                    )
                ),
                vol.Required(CONF_INCLUDE_MODE, default=False): BooleanSelector(),
                vol.Optional(CONF_SELECTED_ENTITIES, default=[]): EntitySelector(
                    EntitySelectorConfig(
                        multiple=True,
                        domain=ALL_SUPPORTED_DOMAINS,
                    )
                ),
                vol.Optional(CONF_DEBOUNCE_TIME, default=DEFAULT_DEBOUNCE_MS): NumberSelector(
                    NumberSelectorConfig(
                        min=50,
                        max=2000,
                        step=50,
                        unit_of_measurement="ms",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        
        return self.async_show_form(
            step_id="user", 
            data_schema=schema, 
            errors=errors,
            description_placeholders={
                "mode_action": "include or exclude"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return OptimisticOptionsFlow(config_entry)


class OptimisticOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        # Get current options with defaults
        current_domains = self.config_entry.options.get(CONF_DOMAINS, DEFAULT_DOMAINS)
        current_include_mode = self.config_entry.options.get(CONF_INCLUDE_MODE, False)
        current_selected_entities = self.config_entry.options.get(CONF_SELECTED_ENTITIES, [])
        current_debounce_time = self.config_entry.options.get(CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_MS)

        if user_input is not None:
            # Check if include mode changed and we need to refresh the form
            if user_input.get(CONF_INCLUDE_MODE) != current_include_mode:
                # Mode changed, show form again with updated UI
                return await self._show_options_form(
                    user_input.get(CONF_DOMAINS, current_domains),
                    user_input.get(CONF_INCLUDE_MODE, False),
                    user_input.get(CONF_SELECTED_ENTITIES, []),
                    user_input.get(CONF_DEBOUNCE_TIME, current_debounce_time),
                    errors
                )
            
            return self.async_create_entry(title="", data=user_input)

        return await self._show_options_form(
            current_domains, current_include_mode, current_selected_entities, current_debounce_time, errors
        )

    async def _show_options_form(self, domains, include_mode, selected_entities, debounce_time, errors):
        """Show the options form with dynamic labels based on include/exclude mode."""
        
        # Create entity selector filtered by selected domains
        entity_selector_config = EntitySelectorConfig(
            multiple=True,
            domain=domains if domains else ALL_SUPPORTED_DOMAINS,
        )

        # Dynamic field based on mode
        mode_action = "include" if include_mode else "exclude"
        mode_description = (
            "🟢 Include mode: Only selected entities will receive optimistic feedback." 
            if include_mode else 
            "🔴 Exclude mode: All domain entities except selected ones will receive optimistic feedback."
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_DOMAINS, default=domains): SelectSelector(
                    SelectSelectorConfig(
                        options=ALL_SUPPORTED_DOMAINS,
                        multiple=True,
                        mode="dropdown",
                    )
                ),
                vol.Required(CONF_INCLUDE_MODE, default=include_mode): BooleanSelector(),
                vol.Optional(CONF_SELECTED_ENTITIES, default=selected_entities): EntitySelector(
                    entity_selector_config
                ),
                vol.Optional(CONF_DEBOUNCE_TIME, default=debounce_time): NumberSelector(
                    NumberSelectorConfig(
                        min=50,
                        max=2000,
                        step=50,
                        unit_of_measurement="ms",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "mode_description": mode_description,
                "mode_action": mode_action
            }
        )