---
layout: default
title: Weather stations
nav_order: 9
permalink: /weather
description: How a node with a weather sensor shares wind, temperature, pressure and rain with every node, the web app and ATAK.
---

# Weather stations

A node with a weather sensor wired to it (normally a mast) shares its readings with every node on the mesh. Every node shows every station on its **Weather** page and on the Dashboard, and the node that owns the sensor puts a weather marker on every ATAK map. Nothing has to be set up on the phones.

{: .note }
The software is ready and tested with a simulated sensor. The recommended hardware has not been bench tested yet; see [Open bench questions](#open-bench-questions).

---

## Hardware

The supported sensor is the **DFRobot SEN0657** ultrasonic 7-in-1 (wind speed, wind direction, temperature, humidity, pressure, rain and light). It speaks Modbus-RTU over RS485 and connects to the node through a USB-RS485 adapter (for example the Waveshare FT232RL isolated adapter). It needs 10 to 30 V.

The FTDI and CH341 USB serial drivers are already in the firmware, so the adapter appears as `/dev/ttyUSB0` with no firmware change. Use `/dev/serial/by-id/...` if the node has more than one USB serial device.

Wireless 915 MHz stations such as the Ecowitt WS90 are not supported on purpose: they transmit inside the HaLow band (902 to 928 MHz), which would desense a mast radio and set off jamming detection.

---

## How it works

1. The sensor node reads the sensor every `pollInterval` (5 s). From its history it works out the gust over `gustWindow` (10 min), the pressure change over 3 hours and the rain in the last hour.
2. Every `publishInterval` (30 s) it shares the reading over alfred (datatype 106), with its position when it has a GNSS fix.
3. Every node lists the stations it hears. A station is marked **stale** after `staleAfter` (5 min) without a new reading and dropped after `expiry` (30 min).
4. The sensor node sends one ATAK marker for its own station (see [ATAK map feed](./atak)). Only the owner sends it, so a station never shows twice.

---

## Where it shows

**Web app, Weather page** (`/weather`). One panel per station, this node's first: temperature (°F and °C), wind and gust in mph, direction, humidity, pressure and its 3 h trend, rain in the last hour and in total, light and position. A stale station stays listed but greyed out with its age. A failed sensor shows the error. It works on phones and desktops.

**Web app, Dashboard.** A Weather panel joins the top row when any station is heard. It shows this node's station, or the first fresh one on the mesh.

**ATAK.** A weather station marker labelled like `WX MAST-1 41°F NW 12G20 mph` (temperature, wind direction, speed and gust). Its details list humidity, pressure and trend, rain in the last hour and the time of the reading. The marker is removed when the reading goes stale.

---

## Settings

Every key is optional; the values below are the defaults. Every node lists stations it hears. Only a node with a sensor needs `sensor.enable: true`.

```yaml
weather:
  enable: true              # list stations heard over the mesh
  sensor:
    enable: false           # poll a sensor wired to this node
    model: sen0657          # sen0657, or sim for a simulated sensor
    device: /dev/ttyUSB0    # must be under /dev/
    baud: 4800              # 1200 to 115200, as set on the sensor
    address: 1              # Modbus address, 1 to 247
    pressureScale: 1.0      # raw pressure register x scale = hPa
  pollInterval: 5s          # 1s to 1m
  publishInterval: 30s      # 5s to 5m
  staleAfter: 5m            # 30s to 1h
  expiry: 30m               # 30s to 24h, never shorter than staleAfter
  gustWindow: 10m           # 1m to 1h
tak:
  weather: true             # send this node's station to ATAK
```

A value outside its range is ignored, the default is used, and the daemon logs a warning naming the key.

**Testing without hardware.** Set `weather.sensor.enable: true` and `weather.sensor.model: sim`. The node then reports a simulated station (about 850 hPa, a daily temperature swing and a shower every few hours) to the web app, the mesh and ATAK.

Changes to `weather.*` take effect after `openmanetd` restarts. `tak.weather` applies on the next ATAK feed tick.

---

## Open bench questions

These need the real sensor on the bench before the readings can be trusted:

1. **Pressure unit.** The datasheet does not say whether the pressure register is in hPa, kPa x 10 or Pa / 10. Compare against a known barometer and set `pressureScale` so the web app shows hPa.
2. **Block read.** The node reads registers 0x01F4 to 0x0201 in one request. If the sensor refuses it, the node falls back to two reads by itself; the logs say so.
3. **Light and rain.** Confirm the light register is lux and how the rain counter resets.
4. **Winter.** The SEN0657 has no heater, so ice may stop the ultrasonic wind reading. A heated sensor (Linovision IOT-S300WS7) is the upgrade path.

---

## Troubleshooting

- **Weather page says "No weather stations heard."** No node on the mesh has `weather.sensor.enable: true`, or the sensor node can't reach the mesh. Gossip takes up to `publishInterval` to arrive.
- **Station shows FAIL.** The node can't read the sensor. Check the adapter is at the configured `device`, the baud rate and address match the sensor, and A/B are not swapped.
- **No ATAK marker.** The sensor node needs a position (GNSS fix or attached phone) and a fresh reading, and `tak.weather` must be on.
