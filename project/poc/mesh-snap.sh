#!/bin/sh
# OpenMANET POC mesh snapshot (GHO-31). Read-only.
# Usage: sh mesh-snap.sh > snap-node1-<when>.txt
# Captures the radio links, batman-adv state and the mesh config, so two
# snapshots (before and after a test) can be compared.

has() { command -v "$1" >/dev/null 2>&1; }

echo "== mesh snapshot $(date -u '+%Y-%m-%dT%H:%M:%SZ') $(cat /proc/sys/kernel/hostname)"
echo "-- uptime"; cat /proc/uptime
echo "-- addresses"; ip -br addr
echo "-- iw dev"; iw dev
for i in $(iw dev | awk '$1 == "Interface" { print $2 }'); do
	echo "-- $i station dump"
	iw dev "$i" station dump
	echo "-- $i mesh params"
	iw dev "$i" get mesh_param 2>/dev/null | head -n 40
done
if has batctl; then
	echo "-- batctl if"; batctl if
	echo "-- batctl n"; batctl n
	echo "-- batctl o"; batctl o
	echo "-- batctl gwl"; batctl gwl
	echo "-- batctl multicast forceflood"; batctl mff 2>/dev/null || batctl mm
fi
echo "-- uci wireless"; uci -q show wireless | grep -v -E '\.key='
echo "-- uci network (bat)"; uci -q show network | grep -E 'bat|ahwlan'
echo "-- uci mesh11sd"; uci -q show mesh11sd
echo "-- dmesg (radios, batman)"
dmesg | grep -i -E 'morse|mt7915|ath10k|batman|mesh' | tail -n 40
