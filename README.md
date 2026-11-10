# home-assistant-bosch-custom-component

> **Fork by Schimmelreiter** - based on the original
> [bosch-thermostat/home-assistant-bosch-custom-component](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component)
> **0.29.0b1** (DataUpdateCoordinator, `gateway.py`, device identifiers with `via_device_id`), merged with
> [cydrezz/bosch-custom-component-ha-pro](https://github.com/cydrezz/bosch-custom-component-ha-pro).
> All credit goes to **pszafer** and the contributors of the original, and to **cydrezz** for the statistics
> fixes - please support them, not this fork.
>
> Changes compared to the original 0.29.0b1:
> * long-term statistics (from cydrezz): a failed recorder query aborts the statistics cycle instead of
>   re-importing with a fresh sum; the baseline row of a re-import is searched further back in the recorder
>   (days/hours with 0 kWh have no rows - the old fallback took a row of the rebuilt period and counted it
>   again); recording sensors write 0 kWh rows for quiet hours and skip duplicate hours
> * the XMPP gateway (EasyControl, cloud) is created outside the event loop, so loading the SSL certificates
>   no longer shows up as "blocking call inside the event loop"
> * leftover `print()` output of bosch-thermostat-client 0.28.2 ("sensr ...", "de ...") goes to the debug log
>   instead of the Home Assistant log
> * connection check: one cheap request per refresh; if the gateway stops answering (seen with EasyControl:
>   the XMPP session is lost and every request times out, while the entities kept showing old values for
>   hours), the entities become unavailable after three failed checks and the integration reloads itself to
>   reconnect (at most every 15 minutes). Gateways that never answered the check are not affected.
> * after changing program (preset), target temperature or HVAC mode the gateway is read back once per
>   second until it reports the new value (up to 15 s), instead of reading it immediately - EasyControl
>   still reports the old value right after the change, so HA showed the old program for one scan interval.
>   The log shows how long the confirmation took.
>
> Not taken over from cydrezz: the energy counter unit option for heat pumps (`energyConsumption`), the
> GitHub issue agent and the branding.
>
> **Installation via HACS:** add `https://github.com/Schimmelreiter/bosch-custom-component-ha-pro` as a
> custom repository (category *Integration*). It uses the same domain `bosch`, existing configuration and
> entities are kept; on the first start the original migrates the device identifiers.

HA custom component for Bosch thermostats.
If you like this ha-pro fork consider sponsoring my work: [:heart: Sponsor](https://github.com/sponsors/cydrezz)

This is a maintained fork of [pszafer's bosch-thermostat component](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component) — consider [sponsoring the original author](https://github.com/sponsors/pszafer) too.

**Second maintainer needed!**

**Hi, I'm looking for help to make this component better**
https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/issues/414

**Latest version will only work with Home Assistant 2025.7 and Python >=3.12.**
For older HA look into release notes.

If possible and if it's ok with you please enable Home Assistant Analytics so I can see how many people uses this integration.

Supported protocols:

- XMPP -> connect to bosch cloud!
- HTTP -> connect locally - available only for IVT devices.

Supported types of devices:

- IVT (HTTP/XMPP):
  - RC300
  - RC200
  - RC35
  - RC30
  - RC20
- NEFIT(XMPP only):
  - Junkers CT100
  - Bosch Remote room controller CT100
- EASYCONTROL(XMPP only):
  - Bosch CT200
  - Buderus Logamatic TC100.2

## Installation

Please find an installation guide (https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Home-Assistant-Installation-Guide) in the wiki and further information.

## Manually

Download this repository into your configuration directory.

## HACS

Preferred way. Go to https://hacs.xyz/ and learn more about installation of custom components.

## Configuration

### Integration.

Go to integration page, add Bosch component and follow on going screens.
By default all sensors are disabled!
Go to integration device `Bosch sensors` and enable sensor you'd like to see.
If you have troubles, go to **wiki** and read more detailed installation instructions.

# Help

Any help appreciated.
Open PR or issue.

Always attach debugscan if you have any troubles or something is missing.
To make debugscan go to HA developer tools -> Services and choose

## Setup fails with "Unable to decrypt" or "Wrong IP or credentials"

If the credentials look correct but setup still fails with a decryption error, the usual
cause on **Buderus KM100 / KM200** gateways is that the device password was never actually
written to the gateway.

The **MyBuderus** app pairs via the QR code on the device and does not need the device
password — but it still prompts you to set one, and does not save it. The separate
**Buderus MyDevice** app connects locally and does set it.

Also note the device password is neither your SingleKey ID nor your MyBuderus account
password.

Full walkthrough, including a command to verify the password before retrying in Home
Assistant: [Setting the device password on Buderus gateways](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Home-Assistant-Installation-Guide#setting-the-device-password-on-buderus-gateways-km100-km200)

## Home Assistant debugging log

In case of a working integration within Home Assistant you may find issues in the way the Bosch environment is visible within HA. To identify the root cause, a debug log is helpful. To obtain these log, please follow the guidenance in the wiki https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Home-Assistant-Obtain-Debug-Logs.

Example logger config for debugging:

```
logger:
  default: warning
  logs:
    custom_components.bosch: debug
    bosch_thermostat_client: debug
```

## Bosch system scan via raw scan

The integration allows a raw scan of the connected Bosch devices via Home Assistant or Linux system. This is useful, if your installation fails or does not show devices or sensors you know to be existing.

Detailed guidance can be found at https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Trace-File-of-Communication-with-Bosch-Device-(Dev-Raw-Scan)

**bosch.debug_scan** .

Download `json` file and attach it somewhere. The `json` file is stored under <hass-config>/www/bosch_scan.json. Please make sure the www folder exists prior to running the scan.

# First config help needed.

Come to Discord channel https://discord.gg/WeWQGNR and let's try to figure out if you have unknown device for us or if there is issue with component.

## ha-pro option: raw unit of the energy counter

`/heatSources/energyMonitoring/consumption` is labelled "kWh" by every gateway,
but the real scale differs per appliance (kWh on KM100/KM200 boilers, J on a
WLW196-11 heat pump behind an nsc_icom gateway, Wh reported for a CW400).
Since it cannot be detected, it is an option per gateway
(Settings -> Integrations -> Bosch -> Configure): kWh (default: raw value,
rounded to 3 decimals, otherwise as upstream), Wh, kJ or J. Fork releases
0.28.8.3 to 0.28.8.5 divided by 3.6 million for everyone; since 0.28.8.6
WLW196/nsc_icom users set the option to J once. Compare `sensor.energy_consumption` with your app:
about 1000x too high = Wh, 3600x = kJ, millions of times = J. A log warning
appears once when the raw value is implausible for kWh.
