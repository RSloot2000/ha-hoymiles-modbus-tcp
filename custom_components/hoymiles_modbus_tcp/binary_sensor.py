# custom_components/hoymiles_modbus_tcp/binary_sensor.py

import logging
from homeassistant.components.binary_sensor import BinarySensorEntity

from .ha_hoymiles_dtu import HAHoymilesDTU

_LOGGER = logging.getLogger(__name__)
DOMAIN = "hoymiles_modbus_tcp"


async def async_setup_entry(hass, config_entry, async_add_entities):
    client = hass.data[DOMAIN][config_entry.entry_id]
    dtu = HAHoymilesDTU(hass, DOMAIN, client)

    await dtu.map_microinverters()
    await dtu.fetch_serial_number()

    sid = dtu.sid
    device_info = dtu.device_info

    entities = []
    for mi in client.microinverters:
        inv_device = {
            "identifiers": {(DOMAIN, f"{sid}_{mi.serial_number}")},
            "name": f"Hoymiles Microinverter {mi.serial_number}",
            "manufacturer": "Hoymiles",
            "model": "Microinverter",
            "via_device": (DOMAIN, sid),
        }
        for idx, panel in enumerate(mi.panels):
            entities.append(
                HoymilesAlarmSensor(client, sid, mi.serial_number, idx, panel, inv_device)
            )
    async_add_entities(entities)


class HoymilesAlarmSensor(BinarySensorEntity):
    """One binary sensor per inverter: on while an alarm code is reported."""

    def __init__(self, client, sid, serial, idx, panel, device_info):
        _LOGGER.debug(f"[binary_sensor] Creating alarm sensor for {serial} #{idx + 1}")
        self._client = client
        self._read = panel.get_alarm_code
        self._state = False
        self._attr_name = f"{serial} #{idx + 1} Alarm"
        self._attr_unique_id = f"{sid}_{serial}_p{idx}_alarm"
        self._attr_device_info = device_info
        self._attr_icon = "mdi:alert"
        self._attr_should_poll = True

    @property
    def is_on(self):
        return self._state

    @property
    def scan_interval(self):
        return 60

    async def async_update(self):
        try:
            self._state = bool(await self._read())
        except Exception as e:
            _LOGGER.error(f"[binary_sensor] Alarm {self._attr_name}: read failed: {e}")
