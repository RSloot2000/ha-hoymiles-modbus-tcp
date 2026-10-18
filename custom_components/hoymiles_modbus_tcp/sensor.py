# custom_components/hoymiles_modbus_tcp/sensor.py

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfPower, UnitOfEnergy  # Updated imports for units
import time


# from .hoymiles_dtu_client import HoymilesClient
from .ha_hoymiles_dtu import HAHoymilesDTU


_LOGGER = logging.getLogger(__name__)
DOMAIN = "hoymiles_modbus_tcp"


async def async_setup_entry(hass, config_entry, async_add_entities):
    dtu = HAHoymilesDTU(hass, DOMAIN, hass.data[DOMAIN][config_entry.entry_id])

    await dtu.map_microinverters()
    await dtu.fetch_serial_number()
    

    device_info = dtu.device_info
    sid = dtu.sid
    name = dtu.name
    _LOGGER.debug(f"Setting up Hoymiles DTU with SID {sid} and name {name}")

    client = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        HoymilesStationPowerSensor(client, name, sid, device_info),
        HoymilesStationDailyEnergySensor(client, name, sid, device_info),
        HoymilesStationTotalEnergySensor(client, name, sid, device_info),
    ]

    # Per-inverter sensors: one device group per microinverter, exposing every
    # readable register on each of its strings/panels.
    for mi in client.microinverters:
        inv_device = {
            "identifiers": {(DOMAIN, f"{sid}_{mi.serial_number}")},
            "name": f"Hoymiles Microinverter {mi.serial_number}",
            "manufacturer": "Hoymiles",
            "model": "Microinverter",
            "via_device": (DOMAIN, sid),
        }
        for idx, panel in enumerate(mi.panels):
            entities.extend(
                _build_inverter_sensors(client, sid, mi.serial_number, idx, panel, inv_device)
            )

    async_add_entities(entities)



class HoymilesStationPowerSensor(SensorEntity):
    def __init__(self, client, name, sid, device_info):
        self._client = client
        self._sid = sid
        self._attr_name = f"{name} Current Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_unique_id = f"{sid}_power"
        self._attr_device_class = "power"
        self._attr_state_class = "measurement"
        self._attr_icon = "mdi:solar-power"
        self._attr_native_value = None  # Initial value, will be updated in async_update
        self._attr_should_poll = True
        self._attr_device_info = device_info
        self._state = None
        self_last_update = time.time()

    @property
    def native_value(self):
        return self._state
    
    @property
    def scan_interval(self):
        """Return the scan interval in seconds."""
        return 120


    async def async_update(self):
        _LOGGER.debug(f"Fetching current power for station {self._sid}")
        power = await self._client.get_total_power()
        _LOGGER.debug(f"Received power data for station {self._sid}: {power/1000} kW")
        self._state = float(power)


class HoymilesStationDailyEnergySensor(SensorEntity):
    def __init__(self, client, name, sid, device_info):
        self._client = client
        self._sid = sid
        self._attr_name = f"{name} Daily Energy"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_unique_id = f"{sid}_daily_energy"
        self._attr_device_class = "energy"
        self._attr_state_class = "total_increasing"
        self._attr_icon = "mdi:solar-power"
        self._attr_native_value = None
        self._attr_should_poll = True
        self._attr_device_info = device_info
        self._state = None

    @property
    def native_value(self):
        return self._state

    @property
    def scan_interval(self):
        """Return the scan interval in seconds."""
        return 120

    async def async_update(self):
        #only update the daily energy once every 2 minutes
        if self._state is not None and (time.time() - self._last_update < 120):
            _LOGGER.debug(f"Skipping update for station {self._sid}, last update was too recent.")
            return
        self._last_update = time.time()


        _LOGGER.debug(f"Fetching daily energy for station {self._sid}")
        daily_energy = await self._client.get_daily_power()
        _LOGGER.debug(f"Received daily energy data for station {self._sid}: {daily_energy} kWh")
        self._state = float(daily_energy)/1000
        # Convert to kWh


async def _kwh(coro):
    """Await a Wh-producing coroutine and return the value in kWh."""
    return (await coro) / 1000.0


def _build_inverter_sensors(client, sid, serial, idx, panel, device_info):
    """Build every per-inverter sensor for one panel/string."""
    def mk(key, label, unit, device_class, state_class, icon, coro):
        return _PerInverterSensor(
            client,
            name=f"{serial} #{idx + 1} {label}",
            unique_id=f"{sid}_{serial}_p{idx}_{key}",
            device_info=device_info,
            unit=unit,
            device_class=device_class,
            state_class=state_class,
            icon=icon,
            read_coro=coro,
        )

    return [
        mk("pv_voltage", "PV Voltage", "V", "voltage", "measurement", "mdi:voltage", panel.get_pv_voltage),
        mk("pv_current", "PV Current", "A", "current", "measurement", "mdi:current-ac", panel.get_pv_current),
        mk("grid_voltage", "Grid Voltage", "V", "voltage", "measurement", "mdi:voltage", panel.get_grid_voltage),
        mk("grid_frequency", "Grid Frequency", "Hz", "frequency", "measurement", "mdi:frequency", panel.get_grid_frequency),
        mk("pv_power", "PV Power", "W", "power", "measurement", "mdi:solar-power", panel.get_pv_power),
        mk("today_production", "Today Production", "kWh", "energy", "total_increasing", "mdi:counter", lambda: _kwh(panel.get_today_production())),
        mk("total_production", "Total Production", "kWh", "energy", "total_increasing", "mdi:counter", lambda: _kwh(panel.get_total_production())),
        mk("temperature", "Temperature", "°C", "temperature", "measurement", "mdi:thermometer", panel.get_temperature),
        mk("operating_status", "Operating Status", None, None, None, "mdi:state-machine", panel.get_operating_status),
        mk("alarm_code", "Alarm Code", None, None, None, "mdi:alert", panel.get_alarm_code),
        mk("alarm_count", "Alarm Count", None, None, None, "mdi:alert-circle-outline", panel.get_alarm_count),
        mk("link_status", "Link Status", None, None, None, "mdi:signal-variant", panel.get_link_status),
    ]


class _PerInverterSensor(SensorEntity):
    """A single per-inverter sensor backed by an async read callable.

    Reads are delegated to ``read_coro`` (a zero-arg coroutine). Any failure is
    logged and swallowed so a single dead register does not take the polling
    entity down; the entity keeps its last good value until the next poll.
    """

    def __init__(self, client, name, unique_id, device_info, unit, device_class, state_class, icon, read_coro):
        self._client = client
        self._read = read_coro
        self._state = None
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info
        self._attr_should_poll = True
        self._attr_icon = icon
        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if device_class is not None:
            self._attr_device_class = device_class
        if state_class is not None:
            self._attr_state_class = state_class

    @property
    def native_value(self):
        return self._state

    @property
    def scan_interval(self):
        """Seconds between polls. Kept modest; each inverter has few panels."""
        return 60

    async def async_update(self):
        try:
            self._state = await self._read()
        except Exception as e:
            _LOGGER.error(f"[sensor] {self._attr_name}: read failed: {e}")


class HoymilesStationTotalEnergySensor(SensorEntity):
    """Station lifetime energy: sum of every inverter's total production."""

    def __init__(self, client, name, sid, device_info):
        self._client = client
        self._sid = sid
        self._state = None
        self._attr_name = f"{name} Total Energy"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_unique_id = f"{sid}_total_energy"
        self._attr_device_class = "energy"
        self._attr_state_class = "total_increasing"
        self._attr_icon = "mdi:solar-power"
        self._attr_should_poll = True
        self._attr_device_info = device_info

    @property
    def native_value(self):
        return self._state

    @property
    def scan_interval(self):
        return 120

    async def async_update(self):
        total_wh = 0
        for mi in self._client.microinverters:
            for panel in mi.panels:
                total_wh += await panel.get_total_production()
        self._state = float(total_wh) / 1000.0