#!/bin/sh
# NanoPC-T6 LTS bench input-power logger (GHO-87, bring-up.md steps 9 and 10).
#
# Reads the INA228 on the pack lead through the kernel's ina238 hwmon driver.
# The chip is declared in the LTS device tree on header I2C8 with its 15 mOhm
# shunt (firmware #55), so the driver already returns scaled values. Also logs
# the SoC temperature and the fan PWM so thermal throttling shows up next to
# the power numbers. Read-only.
#
# Usage, on the node:
#   sh nanopc-power-log.sh [-i s] [-n samples] [-l label] [-H] > power-<test>.csv
#
#   -i  seconds between samples (default 1)
#   -n  stop after this many samples (default 0 = until Ctrl-C)
#   -l  label written in every row, e.g. "idle" or "aw7916_23dbm"
#   -H  omit the CSV header
#
# One CSV row per sample:
#   utc, uptime_s, label, bus_mv, curr_ma, power_mw, energy_j, soc_c, fan_pwm
# SYSFS overrides /sys for testing.

interval=1 count=0 label="" header=1
while getopts i:n:l:H o; do
	case $o in
	i) interval=$OPTARG ;;
	n) count=$OPTARG ;;
	l) label=$OPTARG ;;
	H) header=0 ;;
	*) sed -n '11,16p' "$0" >&2; exit 2 ;;
	esac
done
sys=${SYSFS:-/sys}

find_hwmon() {
	for h in "$sys"/class/hwmon/hwmon*; do
		[ "$(cat "$h/name" 2>/dev/null)" = "$1" ] && { echo "$h"; return 0; }
	done
	return 1
}

ina=$(find_hwmon ina228) || {
	echo "no ina228 hwmon device; check i2cdetect -y 8 and dmesg | grep ina" >&2
	exit 1
}
fan=$(find_hwmon pwmfan) || fan=""
soc=""
for z in "$sys"/class/thermal/thermal_zone*; do
	case $(cat "$z/type" 2>/dev/null) in
	soc-thermal|soc_thermal) soc=$z/temp; break ;;
	esac
done

rd() { [ -n "$1" ] && cat "$1" 2>/dev/null; }

[ "$header" = 1 ] && echo "utc,uptime_s,label,bus_mv,curr_ma,power_mw,energy_j,soc_c,fan_pwm"
i=0
while [ "$count" = 0 ] || [ "$i" -lt "$count" ]; do
	bus=$(rd "$ina/in1_input")
	curr=$(rd "$ina/curr1_input")
	pw=$(rd "$ina/power1_input")
	en=$(rd "$ina/energy1_input")
	t=$(rd "$soc")
	pwm=""
	[ -n "$fan" ] && pwm=$(rd "$fan/pwm1")
	up=$(cut -d" " -f1 /proc/uptime)
	printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
		"$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$up" "$label" "$bus" "$curr" \
		"${pw:+$((pw / 1000))}" "${en:+$((en / 1000000))}" \
		"${t:+$((t / 1000))}" "$pwm"
	i=$((i + 1))
	sleep "$interval"
done
