---
layout: default
title: ATAK map feed
nav_order: 9
permalink: /atak
description: How OpenMANET nodes put themselves, their mesh links, coverage, aircraft, jamming and weather on every ATAK map automatically.
---

# ATAK map feed

Every OpenMANET node puts what it knows on the ATAK map of every phone on the mesh. Nothing has to be installed or configured on the phone.

---

## How it works

ATAK listens on a standard multicast group, the **SA multicast** input at `239.2.3.1:6969`, as soon as it is installed. Anything sent there in Cursor-on-Target (CoT) format shows up on the map.

The mesh is one flat network. Every phone joined to a node's access point or Ethernet port sits in the same broadcast domain as every other node (see [Networking](./networking)), and batman-adv floods multicast to all of them (`batman.multicastForceflood: true`, the default). So when a node sends CoT to that group, every phone on every node receives it.

Each node publishes only what it sees itself. ATAK merges items that share an ID, so a link reported by both of its ends, or an aircraft heard by two nodes, still shows once.

No ATAK plugin is needed. A plugin would only be worth building for things a map item can't show, such as a live spectrum view or controls for the node.

---

## What shows on the map

| Item | Icon | What it tells you |
|---|---|---|
| **Node** | Friendly radio unit | Battery (also on ATAK's battery readout), number of direct mesh links, nodes on the mesh, whether it is the internet gateway, and its web UI address. The details also list the node's health (battery state, CPU temperature, power), each radio (band, frequency, noise floor, how busy the air is, faults), GPS quality (fix, satellites, HDOP), voice (talk group, transmitting), the scanner, the BLOS uplink and channel moves. Anything wrong is listed first on an **ALERT** line. |
| **Mast** | Friendly telecommunications tower | The same details, for a node configured as a fixed mast (`tak.role: mast`). |
| **Mesh link** | Line between two nodes | Green for strong, yellow for ok, red for weak, gray for unknown. These use the same thresholds as the web UI topology map. The details give the signal in dBm and the send rate. Beyond-line-of-sight (BLOS) tunnels are dashed. A link that drops is removed straight away. |
| **Coverage** | Filled square, green, yellow or red | How well the mesh was heard at that spot (see [Coverage heatmap](#coverage-heatmap)). |
| **Aircraft** | Neutral civil aircraft | Callsign, altitude, speed and squawk from a node running the ADS-B scanner. Emergency squawks are flagged. Nearest aircraft are sent first. |
| **Jamming** | Yellow (possible) or red (jamming) jammer symbol | Frequency, noise against baseline, and how busy the channel is. The marker sits on the node that detected it, with a 1 km ring, because the source is somewhere within radio range of that node. It is removed when the jamming stops. |
| **Weather station** | Friendly emplaced sensor | Temperature, wind direction, speed and gust in the label; humidity, pressure and its 3 h trend, and rain in the last hour in the details. Sent only by the node that owns the sensor, and removed when the reading goes stale. See [Weather stations](./weather). |

Markers go stale on their own when a node goes quiet. A node's marker fades after 5 minutes, and an aircraft's after 1 minute.

A node only places itself, its links and its jamming markers when it has a fresh position, under 2 minutes old. That fix can come from its own GNSS receiver or from an attached phone (see [GNSS](./gnss)).

---

## Coverage heatmap

Each node records how well it hears the mesh wherever it goes, using the link signal it already measures. The map is split into square cells (50 m by default). Every 30 seconds, when the node has a GNSS fix at least as good as the cell size, it adds a reading to the cell it is standing in:

| Color | Grade | Meaning |
|---|---|---|
| Green | Good | Best signal at or above -70 dBm, with no dropouts. |
| Yellow | Fair | Best signal at or above -82 dBm, or a strong signal with some dropouts. |
| Red (light) | Weak | A link, but below -82 dBm. |
| Red | No link | No mesh station heard in at least half the readings. A dead spot. |

Tap a cell in ATAK to see which node measured it, the best signal, how many readings it holds and when it was last visited. Every node sends its own cells, so together they show where the whole mesh reaches. A node sends its changed cells first and then cycles through the rest, so a phone that joins late gets the full map within a few minutes.

Cells are saved on the node and survive a restart. Past the cell limit (1024 by default) the cell visited longest ago is dropped. Nodes also share their maps over the mesh every 5 minutes, so the **Coverage** page in any node's web UI shows the whole mesh, with a list of dead spots and their grid references.

---

## Settings

The feed is on by default. Every key is optional, and the values below are the defaults. Changes in `/etc/openmanetd/config.yml` take effect without a restart.

```yaml
tak:
  enable: true
  role: radio        # radio or mast
  interval: 10s      # 2s to 5m; links go out every 3rd interval
  links: true
  jamming: true
  weather: true      # this node's weather station, if it has one
  aircraft:
    enable: true     # needs scanner.enable and an ADS-B receiver
    max: 32          # aircraft per interval, nearest first
    rangeKm: 150     # 0 keeps every aircraft
  coverage:
    enable: true
    cellMeters: 50   # 10 to 500; read at startup, a new size starts a fresh map
    maxCells: 1024   # 64 to 8192; oldest visited cells are dropped first
```

**Network load.** With the defaults, a node sends about one small datagram (300 to 500 bytes) per item every 10 seconds. That covers its own marker, one per neighbor link every 30 seconds, up to 8 coverage cells, up to 32 aircraft, and any active jamming. Lower `aircraft.max` or raise `interval` on a busy HaLow mesh.

**Camera nodes.** A node with a camera already appears as a camera sensor with its video link (see [Camera Support](./hardware/cameras)), so the feed skips its own node marker there. Links, aircraft and jamming are still sent.

**ADS-B.** The optional `adsbcot` package (see [ADS-B to CoT](./adsb-to-cot)) uses the same aircraft IDs. Running both does not double the markers, but it does double the traffic, so the built-in feed is enough on its own.

---

## Troubleshooting

- **Nothing from a node.** Check that the node has a GNSS fix on the GNSS page, and that `tak.enable` is not set to false.
- **Nothing from any node.** In ATAK, check **Settings → Network Preferences → Network Connection Preferences → Manage Inputs** and confirm the default SA multicast input (`239.2.3.1:6969`) is enabled.
- **No coverage cells.** Cells need a GNSS fix at least as accurate as the cell size. Indoors or with a poor fix, the node skips the reading. Check `tak.coverage.enable`.
- **No lines between nodes.** A line needs a position for both ends. The peer's position comes from mesh gossip, which can take up to a minute after it gets a fix.
