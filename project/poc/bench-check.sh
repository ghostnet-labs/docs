#!/bin/sh
# OpenMANET POC bench check for a CM5 node (ekh-bcm2712 image).
#
# Run on the node as root: sh bench-check.sh > check-node1.txt 2>&1
# Prints one PASS/WARN/FAIL line per check, then raw details for the
# GHO-28/GHO-29 records. Read-only: it starts nothing and changes nothing.
# See bring-up-runbook.md for what each failure means.

pass=0 warn=0 fail=0

ok()   { pass=$((pass + 1)); echo "PASS  $*"; }
note() { warn=$((warn + 1)); echo "WARN  $*"; }
bad()  { fail=$((fail + 1)); echo "FAIL  $*"; }

has() { command -v "$1" >/dev/null 2>&1; }

# run_for SECONDS CMD...: run CMD for at most SECONDS and print its output.
run_for() {
	secs=$1; shift
	out=/tmp/bench-check.$$
	"$@" > "$out" 2>&1 &
	p=$!
	sleep "$secs"
	kill "$p" 2>/dev/null
	wait "$p" 2>/dev/null
	cat "$out"; rm -f "$out"
}

# Print the network interfaces whose driver name matches $1.
ifaces_by_driver() {
	for n in /sys/class/net/*; do
		d=$(readlink "$n/device/driver" 2>/dev/null) || continue
		case "${d##*/}" in *$1*) echo "${n##*/}" ;; esac
	done
}

echo "== OpenMANET bench check $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# --- Image and board (GHO-28) ---
board=$(cat /tmp/sysinfo/board_name 2>/dev/null)
[ "$board" = "bcm2712,mm8108-usb" ] && ok "board_name $board" || bad "board_name '$board' (want bcm2712,mm8108-usb)"
model=$( { tr -d '\0' < /proc/device-tree/model; } 2>/dev/null)
case "$model" in *"Compute Module 5"*) ok "model $model" ;; *) note "model '$model'" ;; esac
grep -qs mmcblk0 /proc/cmdline && ok "root on eMMC" || note "root not on mmcblk0: $(cat /proc/cmdline)"

# --- HaLow (GW16167 / MM8108 over USB) ---
halow=$(ifaces_by_driver morse)
if [ -n "$halow" ]; then
	ok "HaLow interface(s): $halow"
else
	bad "no morse netdev (check lsusb, dmesg | grep -i morse, Pier42 cable)"
fi
has morse_cli && { morse_cli -i "${halow%% *}" version >/dev/null 2>&1 && ok "morse_cli version" || note "morse_cli version failed"; }

# --- Wi-Fi (PCIe on the M.2 M-key slot: AW7916-AED mt7915e, D-034) ---
wifi=$(ifaces_by_driver mt7915e)
[ -n "$wifi" ] || wifi=$(ifaces_by_driver ath10k)
[ -n "$wifi" ] && ok "Wi-Fi interface(s): $wifi" || bad "no mt7915e/ath10k netdev (lspci, dmesg | grep -E 'mt7915|ath10k|pcie')"
iw list 2>/dev/null | grep -q 'mesh point' && ok "mesh point supported" || note "no 'mesh point' in iw list"

# --- CM5 onboard Bluetooth ---
if [ -d /sys/class/bluetooth ] && ls /sys/class/bluetooth | grep -q hci; then
	ok "Bluetooth $(ls /sys/class/bluetooth | tr '\n' ' ')"
else
	note "no hci device (CM5 Bluetooth not enabled in the image?)"
fi

# --- GNSS: NMEA over USB-UART, PPS on GPIO18 (GHO-46) ---
gdev=$(uci -q get gpsd.core.device)
[ -c "$gdev" ] && ok "gpsd device $gdev present" || bad "gpsd device '$gdev' missing (Serial Basic plugged in? kmod-usb-serial-ch341?)"
pidof gpsd >/dev/null && ok "gpsd running" || bad "gpsd not running"
[ -c /dev/pps0 ] && ok "/dev/pps0 present" || bad "/dev/pps0 missing (pps-gpio overlay, kmod-pps-gpio)"
if has gpspipe; then
	run_for 10 gpspipe -w | grep -q '"mode":3' && ok "gpsd 3D fix" || note "no 3D fix in 10 s of gpsd reports (sky view?)"
fi
if has ppstest && [ -c /dev/pps0 ]; then
	n=$(run_for 4 ppstest /dev/pps0 | grep -c 'assert')
	[ "$n" -ge 2 ] && ok "PPS pulses ($n in 4 s)" || note "PPS: $n asserts in 4 s (needs a fix; wire on terminal 18?)"
fi

# --- UPS INA219 on i2c-gpio (GPIO22/27) ---
ups=""
for h in /sys/class/hwmon/hwmon*; do
	[ "$(cat "$h/name" 2>/dev/null)" = "ina219" ] && ups=$h
done
if [ -n "$ups" ]; then
	ok "INA219 $ups: $(cat "$ups/in1_input") mV, $(cat "$ups/curr1_input") mA"
else
	bad "no ina219 hwmon (logread -e ina219-ups; i2cdetect on the i2c-gpio bus)"
fi

# --- Ethernet ---
for e in eth0; do
	[ "$(cat /sys/class/net/$e/carrier 2>/dev/null)" = 1 ] \
		&& ok "$e link $(cat /sys/class/net/$e/speed 2>/dev/null) Mb/s" \
		|| bad "$e no carrier"
done

# --- Thermal and throttling (GHO-30) ---
for z in /sys/class/thermal/thermal_zone*; do
	t=$(cat "$z/temp" 2>/dev/null) || continue
	echo "INFO  $(cat "$z/type") $((t / 1000)) C"
done
if has vcgencmd; then
	th=$(vcgencmd get_throttled 2>/dev/null)
	[ "$th" = "throttled=0x0" ] && ok "$th" || note "$th (bit 0 undervoltage, bit 2 throttled; see runbook)"
fi

echo "== $pass pass, $warn warn, $fail fail"

echo
echo "== Details"
cat /etc/openwrt_release 2>/dev/null
uname -a
echo "-- cmdline"; cat /proc/cmdline
echo "-- lsusb"; has lsusb && lsusb
echo "-- lspci"; has lspci && lspci
echo "-- iw dev"; iw dev 2>/dev/null
echo "-- i2c buses"; for b in /sys/bus/i2c/devices/i2c-*; do echo "${b##*/} $(cat "$b/name")"; done
echo "-- gpsd"; uci -q show gpsd
echo "-- dmesg (radios, gnss, i2c, power)"
dmesg | grep -i -E 'morse|ath10k|mt7915|pcie|hci|pps|ttyUSB|ch341|i2c|ina2|under-?voltage|throttl' | tail -n 60

[ "$fail" -eq 0 ]
