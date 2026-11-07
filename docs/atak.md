---
layout: default
title: ATAK map feed
nav_order: 9
permalink: /atak
description: How OpenMANET nodes put themselves, their mesh links, aircraft, jamming and weather on every ATAK map automatically.
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
| **Node** | Friendly radio unit | Battery (also on ATAK's battery readout), number of direct mesh links, nodes on the mesh, whether it is the internet gateway, and its web UI address. |
| **Mast** | Friendly telecommunications tower | The same details, for a node configured as a fixed mast (`tak.role: mast`). |
| **Mesh link** | Line between two nodes | Green for strong, yellow for ok, red for weak, gray for unknown. These use the same thresholds as the web UI topology map. Beyond-line-of-sight (BLOS) tunnels are dashed. A link that drops is removed straight away. |
| **Aircraft** | Neutral civil aircraft | Callsign, altitude, speed and squawk from a node running the ADS-B scanner. Emergency squawks are flagged. Nearest aircraft are sent first. |
| **Jamming** | Yellow (possible) or red (jamming) jammer symbol | Frequency, noise against baseline, and how busy the channel is. The marker sits on the node that detected it, with a 1 km ring, because the source is somewhere within radio range of that node. It is removed when the jamming stops. |
| **Weather station** | Friendly emplaced sensor | Temperature, wind direction, speed and gust in the label; humidity, pressure and its 3 h trend, and rain in the last hour in the details. Sent only by the node that owns the sensor, and removed when the reading goes stale. See [Weather stations](./weather). |

Markers go stale on their own when a node goes quiet. A node's marker fades after 5 minutes, and an aircraft's after 1 minute.

A node only places itself, its links and its jamming markers when it has a fresh position, under 2 minutes old. That fix can come from its own GNSS receiver or from an attached phone (see [GNSS](./gnss)).

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
```

**Network load.** With the defaults, a node sends about one small datagram (300 to 500 bytes) per item every 10 seconds. That covers its own marker, one per neighbor link every 30 seconds, up to 32 aircraft, and any active jamming. Lower `aircraft.max` or raise `interval` on a busy HaLow mesh.

**Camera nodes.** A node with a camera already appears as a camera sensor with its video link (see [Camera Support](./hardware/cameras)), so the feed skips its own node marker there. Links, aircraft and jamming are still sent.

**ADS-B.** The optional `adsbcot` package (see [ADS-B to CoT](./adsb-to-cot)) uses the same aircraft IDs. Running both does not double the markers, but it does double the traffic, so the built-in feed is enough on its own.

---

## Troubleshooting

- **Nothing from a node.** Check that the node has a GNSS fix on the GNSS page, and that `tak.enable` is not set to false.
- **Nothing from any node.** In ATAK, check **Settings → Network Preferences → Network Connection Preferences → Manage Inputs** and confirm the default SA multicast input (`239.2.3.1:6969`) is enabled.
- **No lines between nodes.** A line needs a position for both ends. The peer's position comes from mesh gossip, which can take up to a minute after it gets a fix.
