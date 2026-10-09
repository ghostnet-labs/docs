#!/bin/sh
# OpenMANET bench check for the Ghostnet V1 carrier (bcm2712_ghostnet-v1
# image, board_name ghostnet,v1).
#
# Run on the node as root: sh bench-check-v1.sh > check-v1-<board>.txt 2>&1
# Prints one PASS/WARN/FAIL line per check, then raw details for the
# GHO-19/GHO-21 records. Read-only: it starts nothing, loads nothing and
# drives no GPIO. See bring-up-runbook.md (V1 section) for what a failure
# means. The POC equivalent is bench-check.sh.
#
# The gpio_check lines below follow the canonical GPIO ledger in
# ../hardware/v1-pinout-and-sequencing.md; project/scripts/check_gpio_allocations.py
# fails CI if a signal name here disagrees with it. Expected boot states come
# from the V1 distroconfig in firmware PR 23
# (https://github.com/ghostnet-labs/firmware/pull/23).

pass=0 warn=0 fail=0

ok()   { pass=$((pass + 1)); echo "PASS  $*"; }
note() { warn=$((warn + 1)); echo "WARN  $*"; }
bad()  { fail=$((fail + 1)); echo "FAIL  $*"; }
info() { echo "INFO  $*"; }

has() { command -v "$1" >/dev/null 2>&1; }

# run_for SECONDS CMD...: run CMD for at most SECONDS and print its output.
run_for() {
	secs=$1; shift
	out=/tmp/bench-check-v1.$$
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

# Print the sysfs USB device directories (not interfaces) with VID:PID $1:$2.
usb_by_id() {
	for u in /sys/bus/usb/devices/*; do
		[ -f "$u/idVendor" ] || continue
		[ "$(cat "$u/idVendor")" = "$1" ] || continue
		[ -z "$2" ] || [ "$(cat "$u/idProduct")" = "$2" ] || continue
		echo "$u"
	done
}

echo "== OpenMANET V1 bench check $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# --- Image and board ---
board=$(cat /tmp/sysinfo/board_name 2>/dev/null)
if [ "$board" = "ghostnet,v1" ]; then
	ok "board_name $board"
else
	bad "board_name '$board' (want ghostnet,v1: flash the bcm2712_ghostnet-v1 image)"
fi
info "sysinfo model '$(cat /tmp/sysinfo/model 2>/dev/null)'"
model=$( { tr -d '\0' < /proc/device-tree/model; } 2>/dev/null)
case "$model" in
	*"Compute Module 5"*) ok "model $model" ;;
	*) note "device-tree model '$model' (want a Compute Module 5)" ;;
esac
if grep -qs mmcblk0 /proc/cmdline; then
	ok "root on eMMC"
else
	note "root not on mmcblk0: $(cat /proc/cmdline)"
fi

# --- Wi-Fi: AW7916-AED, MT7916 over PCIe (mt7915e driver) ---
mt=""
for d in /sys/bus/pci/devices/*; do
	[ "$(cat "$d/vendor" 2>/dev/null):$(cat "$d/device" 2>/dev/null)" = "0x14c3:0x7906" ] && mt=$d
done
if [ -n "$mt" ]; then
	ok "PCIe 14c3:7906 (MT7916) at ${mt##*/}"
else
	bad "no PCIe 14c3:7906 (WIFI_PWR_EN high? W_DISABLE1# released? dmesg | grep -i pcie)"
fi
wifi=$(ifaces_by_driver mt7915e)
if [ -n "$wifi" ]; then
	ok "mt7915e interface(s): $(echo "$wifi" | tr '\n' ' ')"
else
	bad "no mt7915e netdev (dmesg | grep -i mt7915; kmod-mt7915e, kmod-mt7916-firmware)"
fi
# Mesh point per Wi-Fi phy. MT7916 normally shows one phy per band.
mesh_phys="" nomesh_phys=""
for i in $wifi; do
	phy=$(cat "/sys/class/net/$i/phy80211/name" 2>/dev/null) || continue
	case " $mesh_phys $nomesh_phys " in *" $phy "*) continue ;; esac
	if iw phy "$phy" info 2>/dev/null | grep -q '\* mesh point'; then
		mesh_phys="$mesh_phys $phy"
	else
		nomesh_phys="$nomesh_phys $phy"
	fi
done
[ -n "$mesh_phys" ] && ok "mesh point supported on$mesh_phys"
[ -n "$nomesh_phys" ] && bad "no 'mesh point' interface mode on$nomesh_phys"
if [ -z "$wifi" ]; then
	if iw list 2>/dev/null | grep -q '\* mesh point'; then
		info "iw list shows mesh point on a non-mt7915e phy"
	else
		note "no 'mesh point' in iw list"
	fi
fi

# Pi 5 / CM5 external PCIe 32-bit DMA limit (raspberrypi/linux#7026, see
# ../hardware/v1-reference.md). The V1 image does not apply the workaround
# overlay by default; a failing card needs dtoverlay=pcie-32bit-dma-pi5.
dmaerr=$(dmesg | grep -i -E 'mt7915|mt7916' | grep -i -E 'fail|error|timeout|dma|swiotlb' | tail -n 5)
if [ -z "$dmaerr" ] && [ -z "$mt" ]; then
	info "no mt7915e messages in dmesg (no card enumerated)"
elif [ -z "$dmaerr" ]; then
	ok "no mt7915e probe/DMA errors in dmesg"
else
	bad "mt7915e errors in dmesg (32-bit DMA limit? try dtoverlay=pcie-32bit-dma-pi5):"
	echo "$dmaerr" | sed 's/^/      /'
fi
for f in /boot/distroconfig.txt /boot/config.txt /boot/usercfg.txt; do
	[ -r "$f" ] || continue
	if grep -qs '^[[:space:]]*dtoverlay=pcie-32bit-dma' "$f"; then
		info "PCIe DMA workaround overlay set in $f"
	else
		info "no pcie-32bit-dma overlay in $f"
	fi
done

# --- USB: CM5 USB 2.0 in dwc2 host mode, TUSB4041I hub (B-04) ---
dwc2bus=""
for u in /sys/bus/usb/devices/usb*; do
	[ "$(cat "$u/product" 2>/dev/null)" = "DWC OTG Controller" ] && dwc2bus=$(cat "$u/busnum")
done
if [ -n "$dwc2bus" ]; then
	ok "dwc2 host controller is USB bus $dwc2bus"
else
	bad "no dwc2 root hub (dtoverlay=dwc2,dr_mode=host in distroconfig? dmesg | grep -i dwc2)"
fi
hub=""
for u in $(usb_by_id 0451 ""); do
	[ "$(cat "$u/bDeviceClass" 2>/dev/null)" = "09" ] || continue
	[ -z "$dwc2bus" ] || [ "$(cat "$u/busnum")" = "$dwc2bus" ] || continue
	hub=$u
done
if [ -n "$hub" ]; then
	ports=$(cat "$hub/maxchild" 2>/dev/null)
	h="TI hub 0451:$(cat "$hub/idProduct") at ${hub##*/}, $ports ports"
	if [ "$ports" = 4 ]; then ok "$h"; else note "$h (TUSB4041I has 4)"; fi
else
	bad "no TI (0451) hub on the dwc2 bus (USB_HUB_RESET_N GPIO23 high? hub 3.3 V and 24 MHz?)"
fi

# --- HaLow: GW16170 / MM8108 over USB on hub port 1 (B-04) ---
halow=$(ifaces_by_driver morse)
if [ -n "$halow" ]; then
	ok "morse interface(s): $(echo "$halow" | tr '\n' ' ')"
	i=$(echo "$halow" | head -n 1)
	udev=$(readlink -f "/sys/class/net/$i/device/.." 2>/dev/null)
	case "${udev##*/}" in
		*.1) ok "HaLow on hub port 1 (${udev##*/})" ;;
		*) note "HaLow USB path '${udev##*/}' (B-04 puts it on hub port 1)" ;;
	esac
	if has morse_cli; then
		if morse_cli -i "$i" version >/dev/null 2>&1; then
			ok "morse_cli version"
		else
			note "morse_cli version failed"
		fi
	fi
else
	bad "no morse netdev (HALOW_PWR_EN GPIO4, HALOW_RESET_N GPIO18 released? dmesg | grep -i morse)"
fi

# --- OpenVLM: CM108B 0d8c:0012 on hub port 3 (B-04, B-22) ---
vlm=$(usb_by_id 0d8c 0012 | head -n 1)
if [ -n "$vlm" ]; then
	case "${vlm##*/}" in
		*.3) ok "OpenVLM 0d8c:0012 on hub port 3 (${vlm##*/})" ;;
		*) note "OpenVLM 0d8c:0012 at '${vlm##*/}' (B-04 puts it on hub port 3)" ;;
	esac
else
	note "no OpenVLM 0d8c:0012 (plugged into the OpenVLM USB-C port? VLM_USB_FAULT_N?)"
fi

# --- Bluetooth: V1 has none (D-026) ---
hci=""
for b in /sys/class/bluetooth/hci*; do [ -e "$b" ] && hci="$hci ${b##*/}"; done
if [ -n "$hci" ]; then
	bad "Bluetooth device(s)$hci present; V1 has none (D-026)"
else
	ok "no hci device (D-026)"
fi

# --- Battery monitor: INA228 on i2c-1 at 0x40 (ina238 driver) ---
ina=/sys/bus/i2c/devices/1-0040
if [ -d "$ina" ]; then
	hw=""
	for h in "$ina"/hwmon/hwmon*; do [ -d "$h" ] && hw=$h; done
	n=$(cat "$hw/name" 2>/dev/null)
	if [ "$n" = "ina228" ]; then
		ok "INA228 ${hw##*/}: $(cat "$hw/in1_input") mV, $(cat "$hw/curr1_input") mA"
	else
		bad "1-0040 present but hwmon name '$n' (want ina228; kmod-hwmon-ina238 loaded?)"
	fi
else
	bad "no i2c 1-0040 (logread -e ina219-ups; i2cdetect -y 1; A0/A1 straps per schematic)"
fi

# --- GNSS: UART0 (/dev/ttyAMA0) to gpsd, PPS on GNSS_PPS GPIO9 ---
gdev=$(uci -q get gpsd.core.device)
case " $gdev " in
	*" /dev/ttyAMA0 "*) ok "gpsd device list '$gdev' uses UART0" ;;
	*) bad "gpsd.core.device '$gdev' does not use /dev/ttyAMA0" ;;
esac
if [ -c /dev/ttyAMA0 ]; then ok "/dev/ttyAMA0 present"; else bad "/dev/ttyAMA0 missing (dtparam=uart0=on)"; fi
if grep -qs 'console=ttyAMA0' /proc/cmdline; then
	bad "kernel console on ttyAMA0, the GNSS UART"
else
	ok "kernel console not on the GNSS UART"
fi
if pidof gpsd >/dev/null; then ok "gpsd running"; else bad "gpsd not running"; fi
if [ -c /dev/pps0 ]; then
	ok "/dev/pps0 present ($(cat /sys/class/pps/pps0/name 2>/dev/null))"
else
	bad "/dev/pps0 missing (dtoverlay=pps-gpio,gpiopin=9; kmod-pps-gpio)"
fi
dbg=/sys/kernel/debug/gpio
if [ -r "$dbg" ]; then
	if grep -E '\(GPIO9 ' "$dbg" | grep -qi pps; then
		ok "pps consumer on GPIO9"
	else
		note "no pps consumer on GPIO9 in $dbg"
	fi
fi
if has gpspipe; then
	if run_for 10 gpspipe -w | grep -q '"mode":3'; then
		ok "gpsd 3D fix"
	else
		note "no 3D fix in 10 s of gpsd reports (sky view?)"
	fi
fi
if has ppstest && [ -c /dev/pps0 ]; then
	n=$(run_for 4 ppstest /dev/pps0 | grep -c 'assert')
	if [ "$n" -ge 2 ]; then ok "PPS pulses ($n in 4 s)"; else note "PPS: $n asserts in 4 s (needs a fix)"; fi
fi

# --- GPIO states (read with pinctrl, which does not change them) ---
# gpio_check GPIO SIGNAL EXPECT
#   out_high  output driven high
#   released  input, line reads high (open-drain release, never driven)
#   input     input, any level
#   idle_high input reading high = not asserted (active-low fault/alert, or
#             active-high good); low is a WARN until GHO-9 pull-ups are verified
#   alt       alternate function (UART, I2C)
#   spare     reserved: must not be an output
#   any       print only
gpio_check() {
	g=$1 sig=$2 want=$3
	line=$(pinctrl get "$g" 2>/dev/null | head -n 1)
	if [ -z "$line" ]; then note "GPIO$g $sig: pinctrl gave nothing"; return; fi
	fn=$(echo "$line" | awk '{print $2}')
	lvl=$(echo "$line" | sed -n 's/.*| *\([a-z]*\).*/\1/p')
	s="GPIO$g $sig: $fn $lvl"
	case "$want" in
		out_high)
			if [ "$fn" = op ] && [ "$lvl" = hi ]; then ok "$s"
			else bad "$s (want output high)"; fi ;;
		released)
			if [ "$fn" = op ]; then bad "$s (output: asserted or driven; want released input)"
			elif [ "$lvl" = hi ]; then ok "$s"
			else bad "$s (want released input reading high)"; fi ;;
		input)
			if [ "$fn" = ip ]; then ok "$s"; else bad "$s (want input)"; fi ;;
		idle_high)
			if [ "$fn" != ip ]; then bad "$s (want input)"
			elif [ "$lvl" = hi ]; then ok "$s"
			else note "$s (low: asserted, or pull-up missing)"; fi ;;
		alt) case "$fn" in a[0-9]*) ok "$s" ;; *) note "$s (want alternate function)" ;; esac ;;
		spare)
			if [ "$fn" = op ]; then note "$s (reserved pin is an output)"; else info "$s"; fi ;;
		*) info "$s" ;;
	esac
}

if has pinctrl; then
	gpio_check 0 Reserved spare
	gpio_check 1 Reserved spare
	gpio_check 2 SYS_I2C_SDA alt
	gpio_check 3 SYS_I2C_SCL alt
	gpio_check 4 HALOW_PWR_EN out_high
	gpio_check 5 WIFI_PWR_EN out_high
	gpio_check 6 HALOW_FAULT_N any
	gpio_check 7 WIFI_FAULT_N any
	gpio_check 8 GNSS_RESET_N any
	gpio_check 9 GNSS_PPS input
	gpio_check 10 SUPERVISOR_WDI any
	gpio_check 11 SUPERVISOR_WDO idle_high
	gpio_check 12 POWER_GOOD idle_high
	gpio_check 13 EFUSE_FAULT idle_high
	gpio_check 14 GNSS_UART_TX alt
	gpio_check 15 GNSS_UART_RX alt
	gpio_check 16 Reserved spare
	gpio_check 17 Reserved spare
	gpio_check 18 HALOW_RESET_N released
	gpio_check 19 HALOW_WAKE_N released
	gpio_check 20 INA228_ALERT_N idle_high
	gpio_check 21 WIFI_WDIS1_N released
	gpio_check 22 Reserved spare
	gpio_check 23 USB_HUB_RESET_N out_high
	gpio_check 24 HALOW_USB_FAULT_N idle_high
	gpio_check 25 VLM_USB_FAULT_N idle_high
	gpio_check 26 Reserved spare
	gpio_check 27 Reserved spare
else
	note "pinctrl missing (bcm27xx-utils); GPIO states not checked"
fi

# --- Ethernet ---
if [ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" = 1 ]; then
	ok "eth0 link $(cat /sys/class/net/eth0/speed 2>/dev/null) Mb/s"
else
	bad "eth0 no carrier"
fi

# --- Thermal and throttling ---
for z in /sys/class/thermal/thermal_zone*; do
	t=$(cat "$z/temp" 2>/dev/null) || continue
	info "$(cat "$z/type") $((t / 1000)) C"
done
if has vcgencmd; then
	th=$(vcgencmd get_throttled 2>/dev/null)
	if [ "$th" = "throttled=0x0" ]; then ok "$th"; else note "$th (bit 0 undervoltage, bit 2 throttled)"; fi
fi

echo "== $pass pass, $warn warn, $fail fail"

echo
echo "== Details"
cat /etc/openwrt_release 2>/dev/null
uname -a
echo "-- cmdline"; cat /proc/cmdline
echo "-- pci"; for d in /sys/bus/pci/devices/*; do echo "${d##*/} $(cat "$d/vendor"):$(cat "$d/device") $(basename "$(readlink "$d/driver" 2>/dev/null)")"; done
echo "-- usb"; for u in /sys/bus/usb/devices/*; do [ -f "$u/idVendor" ] && echo "${u##*/} $(cat "$u/idVendor"):$(cat "$u/idProduct") $(cat "$u/product" 2>/dev/null)"; done
echo "-- iw dev"; iw dev 2>/dev/null
echo "-- i2c buses"; for b in /sys/bus/i2c/devices/i2c-*; do echo "${b##*/} $(cat "$b/name")"; done
echo "-- gpsd"; uci -q show gpsd
echo "-- pinctrl"; has pinctrl && pinctrl get 0-27
echo "-- dmesg (radios, usb, gnss, i2c, power)"
dmesg | grep -i -E 'morse|mt7915|mt7916|pcie|dwc2|usb [0-9]|hub|pps|ttyAMA|i2c|ina2|under-?voltage|throttl' | tail -n 80

[ "$fail" -eq 0 ]
