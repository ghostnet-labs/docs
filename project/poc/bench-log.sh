#!/bin/sh
# OpenMANET POC power and thermal logger for a CM5 node (GHO-30, GHO-31).
#
# Usage: sh bench-log.sh [interval_s] > node1-<test>.csv
# Default interval 5 s. Stop with Ctrl-C. One CSV row per sample:
#   utc            ISO 8601 UTC time
#   uptime_s       seconds since boot
#   cpu_c          CM5 SoC temperature, deg C (thermal_zone0)
#   bat_mv         UPS battery bus voltage, mV (INA219 in1_input)
#   bat_ma         UPS current, mA (INA219 curr1_input; sign per the module wiring)
#   bat_mw         UPS power, mW (INA219 power1_input / 1000)
#   load1          1-minute load average
#   throttled      vcgencmd get_throttled bits, or "na"
#   halow_tx_b     HaLow netdev TX bytes (first morse interface)
#   wifi_tx_b      Wi-Fi netdev TX bytes (first mt7915e or ath10k interface)
# Read-only: it changes no settings.

interval=${1:-5}

first_iface() {
	for n in /sys/class/net/*; do
		d=$(readlink "$n/device/driver" 2>/dev/null) || continue
		case "${d##*/}" in *$1*) echo "${n##*/}"; return ;; esac
	done
}

ups=""
for h in /sys/class/hwmon/hwmon*; do
	[ "$(cat "$h/name" 2>/dev/null)" = "ina219" ] && ups=$h
done
halow=$(first_iface morse)
wifi=$(first_iface mt7915e)
[ -n "$wifi" ] || wifi=$(first_iface ath10k)

rd() { cat "$1" 2>/dev/null || echo ""; }

echo "utc,uptime_s,cpu_c,bat_mv,bat_ma,bat_mw,load1,throttled,halow_tx_b,wifi_tx_b"
while :; do
	t=$(rd /sys/class/thermal/thermal_zone0/temp)
	[ -n "$t" ] && t=$((t / 1000))
	if [ -n "$ups" ]; then
		mv=$(rd "$ups/in1_input"); ma=$(rd "$ups/curr1_input"); uw=$(rd "$ups/power1_input")
		[ -n "$uw" ] && mw=$((uw / 1000)) || mw=""
	else
		mv="" ma="" mw=""
	fi
	if command -v vcgencmd >/dev/null 2>&1; then
		th=$(vcgencmd get_throttled 2>/dev/null); th=${th#throttled=}
	else
		th=na
	fi
	hx=""; [ -n "$halow" ] && hx=$(rd "/sys/class/net/$halow/statistics/tx_bytes")
	wx=""; [ -n "$wifi" ] && wx=$(rd "/sys/class/net/$wifi/statistics/tx_bytes")
	read -r up _ < /proc/uptime
	read -r l1 _ < /proc/loadavg
	echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ'),${up%.*},$t,$mv,$ma,$mw,$l1,$th,$hx,$wx"
	sleep "$interval"
done
