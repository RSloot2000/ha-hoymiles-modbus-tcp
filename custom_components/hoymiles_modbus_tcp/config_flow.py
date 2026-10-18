import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .hoymiles_dtu_client import HoymilesDtuClient

DOMAIN = "hoymiles_modbus_tcp"

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({
    vol.Required("dtu_ip"): str,
    vol.Required("dtu_port", default="502"): str,
})

class HoymilesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _test_connection(self, dtu_ip: str, dtu_port: str) -> bool:
        """Test connection to DTU and return True if successful."""
        try:
            client = HoymilesDtuClient(host=dtu_ip, port=int(dtu_port))
            _LOGGER.debug(f"Testing connection to DTU at {dtu_ip}:{dtu_port}")
            await self.hass.async_add_executor_job(client.test_connection)
            await client.disconnect()
            return True
        except Exception as e:
            _LOGGER.error(f"Connection failed: {e}")
            return False

    def _create_data_schema(self, defaults: dict = None) -> vol.Schema:
        """Create data schema with optional default values."""
        defaults = defaults or {}
        return vol.Schema({
            vol.Required("dtu_ip", default=defaults.get("dtu_ip", "")): str,
            vol.Required("dtu_port", default=defaults.get("dtu_port", "502")): str,
        })

    async def async_step_user(self, user_input=None):
        errors = {}
        try:
            if user_input is not None:
                if await self._test_connection(user_input["dtu_ip"], user_input["dtu_port"]):
                    return self.async_create_entry(title="Hoymiles Modbus TCP", data=user_input)
                errors["base"] = "cannot_connect"
        except Exception:
            # Surface any unexpected failure as a form error instead of a 500.
            _LOGGER.exception("Unexpected error configuring Hoymiles DTU")
            errors["base"] = "unexpected"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        try:
            return HoymilesOptionsFlowHandler(config_entry)
        except Exception:
            # Instantiating the handler must never take down the flow UI. Log the
            # full exception here (this reveals the real root cause) and fall back
            # to a minimal handler so the cogwheel opens instead of returning 500.
            _LOGGER.exception("Error creating the Hoymiles options flow handler")
            return _HoymilesFallbackOptionsFlow(config_entry)

class HoymilesOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        try:
            self.config_entry = config_entry
        except Exception:
            _LOGGER.exception("Error initializing the Hoymiles options flow handler")
            self.config_entry = None

    async def _test_connection(self, dtu_ip: str, dtu_port: str) -> bool:
        """Test connection to DTU and return True if successful."""
        try:
            _LOGGER.debug(f"Testing connection to DTU at {dtu_ip}:{dtu_port}")
            # Create a new client instance for testing
            client = HoymilesDtuClient(host=dtu_ip, port=dtu_port)
            _LOGGER.debug("Testing connection to Hoymiles DTU...")

            result = await client.test_connection()
            await client.disconnect()
            return result
        except Exception as e:
            _LOGGER.error(f"Connection failed: {e}")
            return False

    def _create_data_schema(self, defaults: dict = None) -> vol.Schema:
        """Create data schema with optional default values."""
        defaults = defaults or {}
        return vol.Schema({
            vol.Required("dtu_ip", default=defaults.get("dtu_ip", "")): str,
            vol.Required("dtu_port", default=defaults.get("dtu_port", "502")): str,
        })

    async def async_step_init(self, user_input=None):
        try:
            if user_input is not None:
                if await self._test_connection(user_input["dtu_ip"], user_input["dtu_port"]):
                    # Save the updated options
                    self.hass.config_entries.async_update_entry(self.config_entry, data=user_input)
                    return self.async_create_entry(title="", data={})
                errors = {"base": "cannot_connect"}
            else:
                errors = {}

            # Pre-fill the form with existing values
            return self.async_show_form(
                step_id="init",
                data_schema=self._create_data_schema(self.config_entry.data),
                errors=errors,
            )
        except Exception:
            # Surface any unexpected failure as a form error instead of a 500.
            # DATA_SCHEMA is module-level and already constructed, so this fallback
            # cannot itself fail and guarantees we never escape to a 500.
            _LOGGER.exception("Unexpected error opening the Hoymiles options flow")
            return self.async_show_form(
                step_id="init",
                data_schema=DATA_SCHEMA,
                errors={"base": "unexpected"},
            )


class _HoymilesFallbackOptionsFlow(config_entries.OptionsFlow):
    """Emergency options flow, used only if HoymilesOptionsFlowHandler fails to
    instantiate. Renders the same DTU settings form and saves via
    async_update_entry, without depending on anything the main handler could not
    build."""

    def __init__(self, config_entry=None):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        try:
            if user_input is not None:
                entry = self._config_entry
                if entry is not None:
                    self.hass.config_entries.async_update_entry(entry, data=user_input)
                return self.async_create_entry(title="", data={})

            defaults = self._config_entry.data if self._config_entry else {}
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({
                    vol.Required("dtu_ip", default=(defaults or {}).get("dtu_ip", "")): str,
                    vol.Required("dtu_port", default=(defaults or {}).get("dtu_port", "502")): str,
                }),
            )
        except Exception:
            _LOGGER.exception("Error in fallback Hoymiles options flow")
            return self.async_show_form(
                step_id="init",
                data_schema=DATA_SCHEMA,
                errors={"base": "unexpected"},
            )