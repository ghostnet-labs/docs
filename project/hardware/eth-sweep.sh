#!/bin/sh
# V1 Ethernet speed sweep with iperf3 throughput (GHO-23, tests ET-1 to ET-3).
#
# Usage, on the node as root, from the serial console or a radio link (each
# step renegotiates the link, so an SSH session over this port drops):
#   sh eth-sweep.sh -s <iperf3 server> [-i iface] [-t seconds] [-w link_wait_s] > eth-sweep.csv
#
#   -s  iperf3 server on the bench, reachable through this port (required;
#       run "iperf3 -s" there)
#   -i  interface (default eth0)
#   -t  iperf3 duration per direction in seconds (default 30)
#   -w  seconds to wait for link after each change (default 15)
#   -S  speeds to sweep, space separated (default "10 100 1000")
#
# Each speed is reached with autonegotiation by advertising only that speed at
# full duplex (1000BASE-T cannot be forced). One CSV row per speed and direction:
#   utc         ISO 8601 UTC time
#   iface       interface
#   advertised  speed advertised, Mb/s
#   speed       negotiated speed from sysfs, Mb/s
#   duplex      negotiated duplex
#   link_s      seconds from the change to carrier up (blank = no link in -w)
#   dir         tx (node sends) or rx (node receives, iperf3 -R)
#   mbps        iperf3 receiver-side throughput, Mbit/s
#   retr        TCP retransmits reported on the sender line, or blank
#   err_delta   rx_errors + tx_errors + rx_crc_errors increase during the test
#   result      OK, NOLINK, WRONGSPEED or IPERFFAIL (pass criteria are in
#               v1-validation-procedures.md, not here)
# At the end it restores advertisement of 10/100 half and full and 1000 full.
# It changes only the advertised link modes of the chosen interface.

iface=eth0 server="" dur=30 wait=15 speeds="10 100 1000"
while getopts s:i:t:w:S: o; do
	case $o in
	s) server=$OPTARG ;;
	i) iface=$OPTARG ;;
	t) dur=$OPTARG ;;
	w) wait=$OPTARG ;;
	S) speeds=$OPTARG ;;
	*) sed -n '4,14p' "$0" >&2; exit 2 ;;
	esac
done
[ -n "$server" ] || { sed -n '4,14p' "$0" >&2; exit 2; }
for c in ethtool iperf3; do
	command -v "$c" >/dev/null 2>&1 || { echo "$c not found" >&2; exit 2; }
done
net=/sys/class/net/$iface
[ -d "$net" ] || { echo "no interface $iface" >&2; exit 2; }

# ethtool advertise masks: 10baseT/Full 0x002, 100baseT/Full 0x008, 1000baseT/Full 0x020.
mask() {
	case $1 in 10) echo 0x002 ;; 100) echo 0x008 ;; 1000) echo 0x020 ;; *) echo "" ;; esac
}
restore() { ethtool -s "$iface" autoneg on advertise 0x02f 2>/dev/null; }
trap 'restore; exit 1' INT TERM

rd() { cat "$1" 2>/dev/null || echo 0; }
errs() { echo $(( $(rd "$net/statistics/rx_errors") + $(rd "$net/statistics/tx_errors") + $(rd "$net/statistics/rx_crc_errors") )); }
utc() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

# iperf3 prints e.g.
#   [  5]   0.00-30.00  sec  3.28 GBytes   939 Mbits/sec    12             sender
#   [  5]   0.00-30.04  sec  3.28 GBytes   938 Mbits/sec                  receiver
# Print "mbps,retr" from the receiver and sender summary lines.
iperf_parse() {
	awk '
		/sender$/   { for (i = 1; i <= NF; i++) if ($i ~ /bits\/sec$/) { r = (i + 1 < NF) ? $(i + 1) : "" } }
		/receiver$/ { for (i = 1; i <= NF; i++) if ($i ~ /bits\/sec$/) {
			v = $(i - 1); u = $i
			if (u ~ /^Gbits/) v *= 1000; else if (u ~ /^Kbits/) v /= 1000; else if (u ~ /^bits/) v /= 1e6
			m = v } }
		END { if (m != "") printf "%.1f,%s\n", m, r }'
}

echo "utc,iface,advertised,speed,duplex,link_s,dir,mbps,retr,err_delta,result"
for sp in $speeds; do
	m=$(mask "$sp")
	[ -n "$m" ] || { echo "unsupported speed $sp" >&2; continue; }
	ethtool -s "$iface" autoneg on advertise "$m"
	sleep 2 # let the PHY drop the old link before polling carrier
	t=0 link=""
	while [ "$t" -lt "$wait" ]; do
		if [ "$(rd "$net/carrier")" = 1 ]; then link=$((t + 2)); break; fi
		sleep 1; t=$((t + 1))
	done
	got=$(rd "$net/speed"); dpx=$(cat "$net/duplex" 2>/dev/null)
	for dir in tx rx; do
		now=$(utc)
		if [ -z "$link" ]; then
			echo "$now,$iface,$sp,,,,$dir,,,,NOLINK"; continue
		fi
		if [ "$got" != "$sp" ]; then
			echo "$now,$iface,$sp,$got,$dpx,$link,$dir,,,,WRONGSPEED"; continue
		fi
		e0=$(errs)
		[ "$dir" = rx ] && rev=-R || rev=""
		# $rev is intentionally unquoted so an empty value adds no argument.
		# shellcheck disable=SC2086
		res=$(iperf3 -c "$server" -t "$dur" -f m $rev 2>/dev/null | iperf_parse)
		e1=$(errs)
		if [ -n "$res" ]; then r=OK; else r=IPERFFAIL; res=","; fi
		echo "$now,$iface,$sp,$got,$dpx,$link,$dir,$res,$((e1 - e0)),$r"
	done
done
restore
