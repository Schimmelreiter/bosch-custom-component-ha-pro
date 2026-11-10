"""Connection check with automatic reconnect, and read-back after changes."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bosch_thermostat_client.exceptions import DeviceException
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch import climate as climate_mod
from custom_components.bosch import coordinator as coord_mod
from custom_components.bosch.climate import BoschThermostat
from custom_components.bosch.const import DOMAIN, UUID
from custom_components.bosch.coordinator import BoschDataUpdateCoordinator


def _gateway(get: AsyncMock) -> MagicMock:
    gw = MagicMock()
    gw._connector.get = get
    gw._db = {"gateway": {"uuid": "/gateway/uuid"}}
    return gw


@pytest.fixture(autouse=True)
def _reset_module_state():
    coord_mod._last_reload.clear()
    coord_mod._probe_known_good.clear()
    yield


async def _coordinator(hass: HomeAssistant, get: AsyncMock, entry_id: str = "e1"):
    entry = MockConfigEntry(domain=DOMAIN, data={UUID: "1"}, entry_id=entry_id)
    entry.add_to_hass(hass)
    return BoschDataUpdateCoordinator(hass, gateway=_gateway(get), uuid="1", entry=entry)


async def test_dead_connection_makes_unavailable_and_reloads(hass: HomeAssistant) -> None:
    """After the check worked once, three failures in a row -> UpdateFailed + one reload."""
    answers = [{"value": "uuid"}] + [DeviceException("timeout")] * 6
    get = AsyncMock(side_effect=answers)
    c = await _coordinator(hass, get)
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        assert await c._async_update_data() is True  # works
        assert await c._async_update_data() is True  # 1st failure
        assert await c._async_update_data() is True  # 2nd failure
        with pytest.raises(UpdateFailed):
            await c._async_update_data()  # 3rd failure
        reload.assert_called_once_with("e1")
        with pytest.raises(UpdateFailed):
            await c._async_update_data()  # still dead, but no 2nd reload within 15 min
        reload.assert_called_once()
    get.assert_awaited_with("/gateway/uuid")


async def test_reload_again_after_interval(hass: HomeAssistant) -> None:
    """A new coordinator (after the reload) keeps the known-good state and may reload again later."""
    get = AsyncMock(side_effect=[{"value": "u"}] + [DeviceException("x")] * 10)
    c = await _coordinator(hass, get)
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        await c._async_update_data()
        for _ in range(2):
            await c._async_update_data()
        with pytest.raises(UpdateFailed):
            await c._async_update_data()
        coord_mod._last_reload["e1"] -= coord_mod.RELOAD_MIN_INTERVAL + 1
        c2 = BoschDataUpdateCoordinator(hass, gateway=c.gateway, uuid="1", entry=c.entry)
        for _ in range(2):
            await c2._async_update_data()
        with pytest.raises(UpdateFailed):
            await c2._async_update_data()
        assert reload.call_count == 2


async def test_check_never_worked_is_ignored(hass: HomeAssistant) -> None:
    """A gateway that never answered the check is not made unavailable by it."""
    get = AsyncMock(side_effect=DeviceException("no such path"))
    c = await _coordinator(hass, get)
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        for _ in range(5):
            assert await c._async_update_data() is True
        reload.assert_not_called()


async def test_recovery_resets_counter(hass: HomeAssistant, caplog) -> None:
    get = AsyncMock(side_effect=[{"value": "u"}, DeviceException("x"), DeviceException("x"),
                                 DeviceException("x"), {"value": "u"}, DeviceException("x")])
    c = await _coordinator(hass, get)
    caplog.set_level(logging.INFO)
    with patch.object(hass.config_entries, "async_schedule_reload"):
        await c._async_update_data()
        await c._async_update_data()
        await c._async_update_data()
        with pytest.raises(UpdateFailed):
            await c._async_update_data()
        assert await c._async_update_data() is True
        assert "answers again" in caplog.text
        assert await c._async_update_data() is True  # counter starts over


def _thermostat(hass: HomeAssistant, obj: MagicMock) -> BoschThermostat:
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    t = BoschThermostat(coordinator=coordinator, uuid="1", bosch_object=obj, gateway=MagicMock())
    t.hass = hass
    t.entity_id = "climate.wohnzimmer"
    t.async_write_ha_state = MagicMock()
    return t


def _zone(programs: list[str]) -> MagicMock:
    obj = MagicMock()
    obj.attr_id = "/zones/zn1"
    obj.set_preset_mode = AsyncMock()
    obj.update_requested_key = AsyncMock()
    obj.update = AsyncMock()
    obj.get_property = MagicMock(return_value={"value": 5})
    reads = iter(programs)
    last = {"v": programs[0]}

    def preset():
        try:
            last["v"] = next(reads)
        except StopIteration:
            pass
        return last["v"]

    type(obj).preset_mode = property(lambda self: preset())
    return obj


async def test_preset_confirmed_after_read_back(hass: HomeAssistant, caplog) -> None:
    """Old program for the first read, new one on the second -> confirmed, then refresh."""
    obj = _zone(["Wohnzimmer Winter", "Wohnzimmer Winter frei"])
    t = _thermostat(hass, obj)
    caplog.set_level(logging.INFO)
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01):
        await t.async_set_preset_mode("Wohnzimmer Winter frei")
        assert await t._confirm_task is True
        await hass.async_block_till_done()
    obj.set_preset_mode.assert_awaited_once_with("Wohnzimmer Winter frei")
    obj.update_requested_key.assert_awaited()
    obj.update.assert_not_awaited()
    t.async_write_ha_state.assert_called()
    t.coordinator.async_request_refresh.assert_awaited_once()
    assert "confirmed by the gateway after" in caplog.text


async def test_preset_not_confirmed_warns(hass: HomeAssistant, caplog) -> None:
    obj = _zone(["Wohnzimmer Winter"])
    t = _thermostat(hass, obj)
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01), patch.object(climate_mod, "CONFIRM_TIMEOUT", 0.05):
        await t.async_set_preset_mode("Wohnzimmer Winter frei")
        assert await t._confirm_task is False
        await hass.async_block_till_done()
    assert "not confirmed by the gateway" in caplog.text
    t.async_write_ha_state.assert_called()
    t.coordinator.async_request_refresh.assert_awaited_once()


async def test_preset_without_program_key_reads_whole_circuit(hass: HomeAssistant) -> None:
    obj = _zone(["A", "B"])
    obj.get_property = MagicMock(return_value={})
    t = _thermostat(hass, obj)
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01):
        await t.async_set_preset_mode("B")
        await t._confirm_task
    obj.update.assert_awaited()
    obj.update_requested_key.assert_not_awaited()


async def test_temperature_confirmed(hass: HomeAssistant) -> None:
    obj = MagicMock()
    obj.attr_id = "/zones/zn1"
    obj.set_temperature = AsyncMock(return_value=True)
    temps = iter([20.0, 21.5])
    obj.update = AsyncMock(side_effect=lambda: setattr(obj, "target_temperature", next(temps)))
    t = _thermostat(hass, obj)
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01):
        await t.async_set_temperature(temperature=21.5)
        assert await t._confirm_task is True
    assert obj.update.await_count == 2


async def test_read_back_error_is_tolerated(hass: HomeAssistant) -> None:
    obj = _zone(["A", "A", "B"])
    obj.update_requested_key = AsyncMock(side_effect=[DeviceException("x"), None, None])
    t = _thermostat(hass, obj)
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01):
        await t.async_set_preset_mode("B")
        assert await t._confirm_task is True


async def test_newer_change_supersedes_without_cancelling(hass: HomeAssistant) -> None:
    """A second change ends the first read-back quietly; nothing is cancelled."""
    obj = _zone(["A", "A", "A", "C"])
    t = _thermostat(hass, obj)
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01):
        await t.async_set_preset_mode("B")
        first = t._confirm_task
        await t.async_set_preset_mode("C")
        second = t._confirm_task
        assert await first is None  # superseded, no write, no refresh of its own
        assert await second is True
        await hass.async_block_till_done()
    assert not first.cancelled()
    t.coordinator.async_request_refresh.assert_awaited_once()


async def test_refresh_runs_outside_the_read_back_task(hass: HomeAssistant) -> None:
    """Removing the entity while the refresh runs must not cancel the refresh."""
    obj = _zone(["A", "B"])
    t = _thermostat(hass, obj)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_refresh() -> None:
        started.set()
        await release.wait()

    t.coordinator.async_request_refresh = AsyncMock(side_effect=slow_refresh)
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01):
        await t.async_set_preset_mode("B")
        assert await t._confirm_task is True
        await started.wait()
        t._confirm_task.cancel()  # task already finished - refresh unaffected
        release.set()
        await hass.async_block_till_done()
    t.coordinator.async_request_refresh.assert_awaited_once()


async def test_unexpected_library_error_is_tolerated(hass: HomeAssistant) -> None:
    obj = _zone(["A", "A", "B"])
    obj.update_requested_key = AsyncMock(side_effect=[TypeError("None"), None, None])
    t = _thermostat(hass, obj)
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01):
        await t.async_set_preset_mode("B")
        assert await t._confirm_task is True
