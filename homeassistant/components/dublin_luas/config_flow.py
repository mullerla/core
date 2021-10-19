"""Config flow for Dublin Luas integration."""
from __future__ import annotations

import logging
from typing import Any

from luas.api import ATTR_INBOUND_VAL, ATTR_OUTBOUND_VAL
from luas.models import LUAS_STOPS, LuasDirection, LuasStops
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

LUAS_DESTINATIONS = {"BRI", "SAN", "PAR", "BRO", "TAL", "SAG", "CON", "TPT"}
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("stop"): vol.In(
            {
                stop["abrev"]: stop["name"]
                for stop in sorted(LUAS_STOPS, key=lambda s: s["name"])
            }
        ),
        vol.Required("direction"): vol.In(
            {ATTR_INBOUND_VAL: ATTR_INBOUND_VAL, ATTR_OUTBOUND_VAL: ATTR_OUTBOUND_VAL}
        ),
        vol.Optional("destination"): vol.In(
            {
                stop["abrev"]: stop["name"]
                for stop in sorted(LUAS_STOPS, key=lambda s: s["name"])
                if stop["abrev"] in LUAS_DESTINATIONS
            }
        ),
        vol.Optional("walk_time"): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    if not LuasStops().stop_exists(data["stop"]):
        raise InvalidLuasStop
    if "destination" in data and not LuasStops().stop_exists(data["destination"]):
        raise InvalidLuasDestination
    if data["direction"] not in [ATTR_INBOUND_VAL, ATTR_OUTBOUND_VAL]:
        raise InvalidDirection
    title = f"{data['direction']} from {data['stop']}"
    if "destination" in data:
        title = f"{title} to {data['destination']}"
    return {"title": title}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dublin Luas."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except InvalidLuasStop:
            errors["base"] = "invalid_stop"
        except InvalidDirection:
            errors["base"] = "invalid_direction"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class InvalidDirection(HomeAssistantError):
    """Error to indicate incorrect direction."""


class InvalidLuasStop(HomeAssistantError):
    """Error to indicate incorrect Luas stop."""


class InvalidLuasDestination(HomeAssistantError):
    """Error to indicate incorrect Luas stop for destination."""
