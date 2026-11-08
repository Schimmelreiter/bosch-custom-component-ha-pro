"""Gateway creation outside the event loop and silenced library prints (fork)."""

import asyncio
from functools import partial

import pytest

from custom_components.bosch.gateway import (
    _build_gateway_in_executor,
    _silence_library_prints,
)


@pytest.mark.asyncio
async def test_xmpp_gateway_built_in_worker_thread_binds_to_running_loop():
    # the real class (conftest patches bosch_thermostat_client.gateway_chooser)
    from bosch_thermostat_client.gateway.easycontrol import EasycontrolGateway

    loop = asyncio.get_running_loop()
    gateway_class = EasycontrolGateway
    gateway = await loop.run_in_executor(
        None,
        partial(
            _build_gateway_in_executor,
            loop,
            gateway_class,
            session=None,
            session_type="XMPP",
            host="123456789",
            access_key="abcdefghijklmnop",
            access_token="token",
            password="password",
        ),
    )
    client = gateway._connector.client
    # bound to Home Assistant's loop, not to a new loop of the worker thread
    assert client.loop is loop
    # CA bundle of the Bosch cloud already loaded, not loaded again on connect
    assert client.ca_certs is None
    assert client.ssl_context.cert_store_stats()["x509_ca"] > 0


def test_library_prints_become_debug_log(caplog, capsys):
    import logging

    _silence_library_prints()
    import bosch_thermostat_client.sensors.sensors as sensors_module

    with caplog.at_level(logging.DEBUG, logger="bosch_thermostat_client"):
        sensors_module.print("sensr", "<class X>")
    assert capsys.readouterr().out == ""
    assert "sensr <class X>" in caplog.text
