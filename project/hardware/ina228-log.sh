#!/bin/sh
# V1 INA228 battery-telemetry logger (GHO-23, tests TM-1 to TM-4).
# Same pattern as ../poc/bench-log.sh, reading the V1 INA228 instead of the
# POC UPS INA219.
#
# Usage, on the node:
#   sh ina228-log.sh [-i interval_s] [-n samples] [-l label] [-a] [-H] > ina228-<test>.csv
#
#   -i  seconds between samples (default 1; fractions need a sleep that takes them)
#   -n  stop after this many samples (default 0 = until Ctrl-C)
#   -l  label written in every row, e.g. the calibrated-meter setpoint "9.0V_2.0A"
#   -a  print only one row: the mean of the -n samples (needs -n), with the label
#   -H  omit the CSV header (for appending setpoints to one file)
#
# One CSV row per sample:
#   utc        ISO 8601 UTC time
#   uptime_s   seconds since boot
#   label      the -l label
#   bus_mv     bus voltage, mV (in1_input)
#   shunt_mv   shunt voltage, mV (in0_input)
#   curr_ma    current, mA (curr1_input)
#   power_mw   power, mW (power1_input / 1000)
#   energy_uj  energy since INA228 power-up, µJ (energy1_input)
#   temp_c     INA228 die temperature, °C (temp1_input / 1000)
#   alarms     names of the *_alarm files reading 1, separated by "+", or blank
# With -a, energy_uj is the last reading, not a mean.
# Units are the hwmon driver's (v1-hw-telemetry-recovery.md §6).
# SYSFS overrides /sys for testing. Read-only: it changes no settings.

sys=${SYSFS:-/sys}
interval=1 count=0 label="" avg=0 header=1
while getopts i:n:l:aH o; do
	case $o in
	i) interval=$OPTARG ;;
	n) count=$OPTARG ;;
	l) label=$OPTARG ;;
	a) avg=1 ;;
	H) header=0 ;;
	*) sed -n '6,13p' "$0" >&2; exit 2 ;;
	esac
done
[ "$avg" = 1 ] && [ "$count" -lt 1 ] && { echo "-a needs -n" >&2; exit 2; }

ina=""
for h in "$sys"/class/hwmon/hwmon*; do
	[ "$(cat "$h/name" 2>/dev/null)" = "ina228" ] && ina=$h
done
[ -n "$ina" ] || { echo "no hwmon device named ina228 under $sys/class/hwmon" >&2; exit 2; }

rd() { cat "$1" 2>/dev/null || echo ""; }

row() {
	mv=$(rd "$ina/in1_input"); sv=$(rd "$ina/in0_input"); ma=$(rd "$ina/curr1_input")
	uw=$(rd "$ina/power1_input"); uj=$(rd "$ina/energy1_input"); tm=$(rd "$ina/temp1_input")
	[ -n "$uw" ] && mw=$((uw / 1000)) || mw=""
	[ -n "$tm" ] && tc=$(awk -v t="$tm" 'BEGIN { printf "%.2f", t / 1000 }') || tc=""
	al=""
	for f in "$ina"/*_alarm; do
		[ "$(rd "$f")" = 1 ] && al="${al:+$al+}${f##*/}"
	done
	read -r up _ < /proc/uptime
	echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ'),${up%.*},$label,$mv,$sv,$ma,$mw,$uj,$tc,$al"
}

[ "$header" = 1 ] && echo "utc,uptime_s,label,bus_mv,shunt_mv,curr_ma,power_mw,energy_uj,temp_c,alarms"
i=0
while [ "$count" -eq 0 ] || [ "$i" -lt "$count" ]; do
	row
	i=$((i + 1))
	if [ "$count" -eq 0 ] || [ "$i" -lt "$count" ]; then sleep "$interval"; fi
done | if [ "$avg" = 1 ]; then
	# Mean of the numeric columns; first timestamp, last energy, union of alarms.
	awk -F, -v OFS=, '
		{ n++; if (n == 1) { u = $1; up = $2; lb = $3 }
		  for (c = 4; c <= 9; c++) if ($c != "") { s[c] += $c; k[c]++ }
		  e = $8; if ($10 != "" && index(al, $10) == 0) al = al (al == "" ? "" : "+") $10 }
		END { for (c = 4; c <= 9; c++) m[c] = k[c] ? sprintf("%.3f", s[c] / k[c]) : ""
		      print u, up, lb, m[4], m[5], m[6], m[7], e, m[9], al }'
else
	cat
fi
