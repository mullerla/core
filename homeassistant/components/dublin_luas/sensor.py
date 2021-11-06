from datetime import timedelta
from functools import partial
import logging

import async_timeout
from luas.api import (
    ATTR_DESTINATION,
    ATTR_DIRECTION,
    ATTR_DUE,
    ATTR_DUE_VAL,
    ATTR_INBOUND_VAL,
    ATTR_STATUS,
    ATTR_TRAMS,
    LuasClient,
    LuasDirection,
    LuasLine,
)
from luas.models import LuasStops, LuasTram

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TIME_MINUTES
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

ICON = "mdi:tram"
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Config entry example."""
    api = hass.data[DOMAIN][entry.entry_id]

    async def async_update_stop_data():
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(30):
                return await hass.async_add_executor_job(
                    partial(api.stop_details, entry.data["stop"])
                )
        except Exception as err:
            _LOGGER.exception("Error while requesting Luas stop details")
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def async_update_status_data():
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                green_status = await hass.async_add_executor_job(
                    partial(api.line_status, LuasLine.Green)
                )
                red_status = await hass.async_add_executor_job(
                    partial(api.line_status, LuasLine.Red)
                )
                return {
                    "green": green_status,
                    "red": red_status,
                }
        except Exception as err:
            _LOGGER.exception("Error while requesting Luas status details")
            raise UpdateFailed(f"Error communicating with API: {err}")

    stop_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="luas_stop_data",
        update_method=async_update_stop_data,
        update_interval=timedelta(seconds=30),
    )

    status_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="luas_status_data",
        update_method=async_update_status_data,
        update_interval=timedelta(seconds=120),
    )

    await stop_coordinator.async_config_entry_first_refresh()
    await status_coordinator.async_config_entry_first_refresh()

    async_add_entities(
        [
            LuasStatusSensor(status_coordinator, "green"),
            LuasStatusSensor(status_coordinator, "red"),
            LuasTramSensor(
                stop_coordinator,
                0,
                entry.data["stop"],
                entry.data["direction"],
                entry.data.get("destination"),
            ),
            LuasTramSensor(
                stop_coordinator,
                1,
                entry.data["stop"],
                entry.data["direction"],
                entry.data.get("destination"),
            ),
            LuasTramSensor(
                stop_coordinator,
                2,
                entry.data["stop"],
                entry.data["direction"],
                entry.data.get("destination"),
            ),
            LuasTramSensor(
                stop_coordinator,
                3,
                entry.data["stop"],
                entry.data["direction"],
                entry.data.get("destination"),
            ),
        ]
    )
    if "walk_time" in entry.data:
        async_add_entities(
            [
                LuasTramWaitSensor(
                    stop_coordinator,
                    entry.data["walk_time"],
                    entry.data["stop"],
                    entry.data["direction"],
                    entry.data.get("destination"),
                )
            ]
        )
    return


class LuasTramSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, coordinator, index, stop, direction, destination=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._index = index
        self._stop = LuasStops().stop(stop)
        self._direction = direction
        self._destination = LuasStops().stop(destination) if destination else None
        self.entity_id = f"sensor.{self.unique_id}"

    @property
    def unique_id(self) -> str:
        if self._destination:
            return f"luas_from_{self._stop['abrev']}_to_{self._destination['abrev']}_{self._direction}_{self._index + 1}".lower()
        else:
            return f"luas_from_{self._stop['abrev']}_{self._direction}_{self._index + 1}".lower()

    @property
    def name(self) -> str:
        if self._destination:
            return f"Luas from {self._stop['name']} to {self._destination['name']} {self._direction}"
        else:
            return f"Luas from {self._stop['name']} {self._direction}"

    @property
    def native_unit_of_measurement(self) -> str:
        return TIME_MINUTES

    @property
    def icon(self) -> str:
        return ICON

    @property
    def available(self) -> bool:
        try:
            return self._get_tram() is not None
        except:
            return False

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._get_tram().due

    @property
    def extra_state_attributes(self):
        tram = self._get_tram()
        return {
            "destination": tram.destination,
            "direction": tram.direction,
            "stop": self._stop["name"],
        }

    def _get_tram(self):
        trams = self.coordinator.data[ATTR_TRAMS]
        trams = [tram for tram in trams if tram[ATTR_DIRECTION] == self._direction]
        if self._destination:
            trams = [
                tram
                for tram in trams
                if tram[ATTR_DESTINATION] == self._destination["name"]
            ]
        due = trams[self._index][ATTR_DUE]
        due = 0 if due == "DUE" else int(due)
        return LuasTram(
            due=due,
            direction=trams[self._index][ATTR_DIRECTION],
            destination=trams[self._index][ATTR_DESTINATION],
        )

    @property
    def device_info(self):
        """Device info."""
        return {
            "identifiers": {
                (
                    DOMAIN,
                    self._stop["abrev"],
                    self._direction,
                    self._destination["abrev"] if self._destination else None,
                )
            },
            "model": self.name,
            "default_name": self.name,
            "entry_type": "service",
        }


class LuasTramWaitSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, coordinator, walk_time, stop, direction, destination=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._walk_time = walk_time
        self._stop = LuasStops().stop(stop)
        self._direction = direction
        self._destination = LuasStops().stop(destination) if destination else None
        self.entity_id = f"sensor.{self.unique_id}"

    @property
    def unique_id(self) -> str:
        if self._destination:
            return f"luas_wait_time_from_{self._stop['abrev']}_to_{self._destination['abrev']}".lower()
        else:
            return f"luas_wait_time_from_{self._stop['abrev']}".lower()

    @property
    def name(self) -> str:
        if self._destination:
            return f"Luas wait time from {self._stop['name']} to {self._destination['name']} {self._direction}"
        else:
            return f"Luas wait time from {self._stop['name']} {self._direction}"

    @property
    def native_unit_of_measurement(self) -> str:
        return TIME_MINUTES

    @property
    def icon(self) -> str:
        return ICON

    @property
    def available(self) -> bool:
        try:
            self._get_next_tram()
            return True
        except:
            return False

    @property
    def state(self):
        """Return the state of the sensor."""
        next_tram = self._get_next_tram()
        if next_tram:
            return self._get_next_tram().due - self._walk_time
        else:
            return "unknown"

    def _get_next_tram(self):
        trams = self._get_trams()
        for tram in trams:
            if tram.due > self._walk_time:
                return tram

    def _get_trams(self):
        trams = self.coordinator.data[ATTR_TRAMS]
        trams = [tram for tram in trams if tram[ATTR_DIRECTION] == self._direction]
        if self._destination:
            trams = [
                tram
                for tram in trams
                if tram[ATTR_DESTINATION] == self._destination["name"]
            ]
        return [
            LuasTram(
                due=0 if tram[ATTR_DUE] == "DUE" else int(tram[ATTR_DUE]),
                direction=tram[ATTR_DIRECTION],
                destination=tram[ATTR_DESTINATION],
            )
            for tram in trams
        ]

    @property
    def device_info(self):
        """Device info."""
        return {
            "identifiers": {
                (
                    DOMAIN,
                    self._stop["abrev"],
                    self._direction,
                    self._destination["abrev"] if self._destination else None,
                )
            },
            "model": self.name,
            "default_name": self.name,
            "entry_type": "service",
        }


class LuasStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, coordinator, line):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._line = line

    @property
    def unique_id(self) -> str:
        return f"luas_status_{self._line}".lower()

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"Luas Status {self._line}".capitalize()

    @property
    def icon(self) -> str:
        return ICON

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data[self._line]

    @property
    def device_info(self):
        """Device info."""
        return {
            "identifiers": {(DOMAIN, "Status")},
            "model": "Dublin Luas Status",
            "default_name": "Dublin Luas Status",
            "entry_type": "service",
        }
