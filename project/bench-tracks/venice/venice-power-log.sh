#!/bin/sh
# Venice bench input-power logger (GHO-85, bring-up.md steps 9 and 10).
#
# Reads an INA228 breakout on the pack lead over i2c-dev, from userspace,
# because our 6.6 kernel has no INA228 hwmon driver. Also reads the Venice
# GSC's own input-voltage channel when it is present. Read-only: it never
# writes an INA228 register, so the chip runs at its power-on defaults
# (continuous bus, shunt and temperature conversion, ADCRANGE 0).
#
# Usage, on the node:
#   sh venice-power-log.sh [-b bus] [-a addr] [-r shunt_ohm] [-i s] [-n samples] [-l label] [-H] > power-<test>.csv
#
#   -b  I2C bus number of the off-board header (default 2; check with i2cdetect -l)
#   -a  INA228 address (default 0x40)
#   -r  shunt resistance in ohms (default 0.015; read the value printed on the breakout)
#   -i  seconds between samples (default 1)
#   -n  stop after this many samples (default 0 = until Ctrl-C)
#   -l  label written in every row, e.g. "idle" or "aw7916_23dbm"
#   -H  omit the CSV header
#
# One CSV row per sample:
#   utc, uptime_s, label, bus_mv, shunt_uv, curr_ma, power_mw, die_c, gsc_vin_mv
# curr_ma and power_mw are computed here from the shunt voltage and -r,
# not read from the INA228's CURRENT/POWER registers (those need SHUNT_CAL,
# which this script never writes). gsc_vin_mv is blank when no GSC hwmon
# input-voltage channel is found.
# I2CTRANSFER and SYSFS override the command and /sys for testing.

bus=2 addr=0x40 rshunt=0.015 interval=1 count=0 label="" header=1
while getopts b:a:r:i:n:l:H o; do
	case $o in
	b) bus=$OPTARG ;;
	a) addr=$OPTARG ;;
	r) rshunt=$OPTARG ;;
	i) interval=$OPTARG ;;
	n) count=$OPTARG ;;
	l) label=$OPTARG ;;
	H) header=0 ;;
	*) sed -n '10,19p' "$0" >&2; exit 2 ;;
	esac
done

i2c=${I2CTRANSFER:-i2ctransfer}
sys=${SYSFS:-/sys}

# rd REG NBYTES: print the register as one unsigned decimal integer.
rd() {
	out=$($i2c -y "$bus" "w1@$addr" "$1" "r$2" 2>/dev/null) || return 1
	v=0
	for b in $out; do v=$(( (v << 8) | b )); done
	echo "$v"
}

# The INA228 identifies itself as TI (0x5449) with device ID 0x228x.
mfr=$(rd 0x3e 2) || { echo "no I2C device at bus $bus addr $addr" >&2; exit 1; }
dev=$(rd 0x3f 2) || exit 1
if [ "$mfr" -ne 21577 ] || [ $(( dev >> 4 )) -ne 552 ]; then
	printf 'device at %s is not an INA228 (mfr 0x%04x, id 0x%04x)\n' "$addr" "$mfr" "$dev" >&2
	exit 1
fi

# Find the GSC's input-voltage channel (label vdd_vin) if hwmon has one.
gsc_vin=""
for l in "$sys"/class/hwmon/hwmon*/in*_label; do
	[ -r "$l" ] || continue
	[ "$(cat "$l")" = "vdd_vin" ] && gsc_vin=${l%_label}_input && break
done

[ "$header" = 1 ] && echo "utc,uptime_s,label,bus_mv,shunt_uv,curr_ma,power_mw,die_c,gsc_vin_mv"

i=0
while [ "$count" = 0 ] || [ "$i" -lt "$count" ]; do
	vbus=$(rd 0x05 3) || exit 1
	vsh=$(rd 0x04 3) || exit 1
	temp=$(rd 0x06 2) || exit 1
	# VBUS and VSHUNT are 20-bit values in bits 23:4. VSHUNT and DIETEMP
	# are two's complement.
	vbus=$(( vbus >> 4 ))
	vsh=$(( vsh >> 4 ))
	[ "$vsh" -ge 524288 ] && vsh=$(( vsh - 1048576 ))
	[ "$temp" -ge 32768 ] && temp=$(( temp - 65536 ))
	gv=""
	[ -n "$gsc_vin" ] && gv=$(cat "$gsc_vin" 2>/dev/null)
	up=$(cut -d' ' -f1 /proc/uptime 2>/dev/null)
	# LSBs (INA228 data sheet, ADCRANGE 0): VBUS 195.3125 uV, VSHUNT
	# 312.5 nV, DIETEMP 7.8125 m°C.
	awk -v t="$(date -u +%Y-%m-%dT%H:%M:%SZ)" -v up="$up" -v lb="$label" \
	    -v vb="$vbus" -v vs="$vsh" -v tc="$temp" -v r="$rshunt" -v gv="$gv" 'BEGIN {
		bus_mv = vb * 0.1953125
		sh_uv = vs * 0.3125
		ma = sh_uv / 1000 / r
		printf "%s,%s,%s,%.1f,%.2f,%.1f,%.0f,%.2f,%s\n", t, up, lb,
		    bus_mv, sh_uv, ma, bus_mv * ma / 1000, tc * 0.0078125, gv
	}'
	i=$(( i + 1 ))
	[ "$count" != 0 ] && [ "$i" -ge "$count" ] && break
	sleep "$interval"
done
