#!/bin/sh
# Ghostnet V1 radio validation (GHO-22). Run on the node as root.
#
#   sh v1-radio-validate.sh capture > radios-<board>.txt 2>&1
#       Read-only. Radio identities, firmware versions, `iw phy` modes and
#       bands, mesh point per band, regulatory domain.
#
#   sh v1-radio-validate.sh loop <test> <iterations> > loop-<test>.txt 2>&1
#       Resets or power-cycles one radio N times and logs one PASS/FAIL line
#       per iteration with the recovery times. Tests follow the recovery
#       ladder in ../software/v1-hw-telemetry-recovery.md sections 4 and 5:
#
#       wifi-pci-reset   step 1w: PCI function reset (sysfs reset)
#       wifi-pci-rescan  step 1w: PCI remove, then bus rescan
#       halow-usb-reset  step 1:  USB device reset of the GW16170
#       hub-reset        step 2:  USB_HUB_RESET_N pulse          (drives GPIO)
#       wifi-power       step 3:  WIFI_3V3 off/on via WIFI_PWR_EN (drives GPIO)
#       halow-power      step 3:  HALOW_3V3 off/on via HALOW_PWR_EN (drives GPIO)
#
#   Tests marked "drives GPIO" refuse to run unless ALLOW_GPIO=1 is set. Set it
#   only after GHO-21 has verified the line's polarity and the no-back-feed
#   checks on this board (v1-first-power.md section 4; recovery doc T1/T2).
#   Open-drain lines (HALOW_RESET_N, HALOW_WAKE_N, WIFI_WDIS1_N) are only ever
#   driven low or released to input, never driven high.
#
# GPIO numbers below come from the canonical ledger,
# ../hardware/v1-pinout-and-sequencing.md. Timings default to the proposal in
# the recovery doc section 4 and can be overridden through the environment.

HALOW_PWR_EN=4
WIFI_PWR_EN=5
HALOW_RESET_N=18
USB_HUB_RESET_N=23

# Recovery doc section 4 (seconds; integers, busybox sleep).
OFF_S=${OFF_S:-2}               # minimum rail off time
WIFI_PCI_TIMEOUT=${WIFI_PCI_TIMEOUT:-5}
WIFI_NETDEV_TIMEOUT=${WIFI_NETDEV_TIMEOUT:-20}
HALOW_USB_TIMEOUT=${HALOW_USB_TIMEOUT:-10}
HALOW_NETDEV_TIMEOUT=${HALOW_NETDEV_TIMEOUT:-30}
SETTLE_S=${SETTLE_S:-1}         # rail settle before release; the doc's 20/100 ms rounded up to busybox sleep
PEER_TIMEOUT=${PEER_TIMEOUT:-60} # mesh peer must return if one was up before
GAP_S=${GAP_S:-10}              # pause between iterations

has() { command -v "$1" >/dev/null 2>&1; }
now() { awk '{ printf "%.1f", $1 }' /proc/uptime; }
since() { awk -v a="$1" '{ printf "%.1f", $1 - a }' /proc/uptime; }

# Print the network interfaces whose driver name matches $1.
ifaces_by_driver() {
	for n in /sys/class/net/*; do
		d=$(readlink "$n/device/driver" 2>/dev/null) || continue
		case "${d##*/}" in *$1*) echo "${n##*/}" ;; esac
	done
}

# Print the PCI address of the MT7916 (14c3:7906).
mt7916_bdf() {
	for d in /sys/bus/pci/devices/*; do
		[ "$(cat "$d/vendor" 2>/dev/null):$(cat "$d/device" 2>/dev/null)" = "0x14c3:0x7906" ] && echo "${d##*/}"
	done
}

# Print the sysfs USB device directory under the first morse netdev.
halow_usbdev() {
	i=$(ifaces_by_driver morse | head -n 1)
	[ -n "$i" ] || return 1
	readlink -f "/sys/class/net/$i/device/.."
}

# wait_for SECONDS CMD...: poll CMD every second until it succeeds or time
# runs out. Returns CMD's last status.
wait_for() {
	t=$1; shift
	while :; do
		"$@" && return 0
		[ "$t" -le 0 ] && return 1
		sleep 1
		t=$((t - 1))
	done
}

have_wifi_netdev()  { [ -n "$(ifaces_by_driver mt7915e)" ]; }
have_halow_netdev() { [ -n "$(ifaces_by_driver morse)" ]; }
have_pci()          { [ -n "$(mt7916_bdf)" ]; }
have_path()         { [ -e "$1" ]; }

# --- capture (read-only) ---

capture() {
	echo "== V1 radio capture $(date -u '+%Y-%m-%dT%H:%M:%SZ') $(cat /tmp/sysinfo/board_name 2>/dev/null)"
	cat /etc/openwrt_release 2>/dev/null
	uname -a

	echo "-- PCI devices"
	for d in /sys/bus/pci/devices/*; do
		echo "${d##*/} $(cat "$d/vendor"):$(cat "$d/device") sub $(cat "$d/subsystem_vendor"):$(cat "$d/subsystem_device") driver=$(basename "$(readlink "$d/driver" 2>/dev/null)")"
		has lspci && lspci -s "${d##*/}" -vv 2>/dev/null | grep -E 'LnkCap:|LnkSta:'
	done
	echo "-- USB devices"
	for u in /sys/bus/usb/devices/*; do
		[ -f "$u/idVendor" ] || continue
		echo "${u##*/} $(cat "$u/idVendor"):$(cat "$u/idProduct") speed=$(cat "$u/speed") $(cat "$u/manufacturer" 2>/dev/null) $(cat "$u/product" 2>/dev/null)"
	done

	echo "-- netdevs and drivers"
	for n in /sys/class/net/*; do
		d=$(readlink "$n/device/driver" 2>/dev/null) || continue
		echo "${n##*/} driver=${d##*/} phy=$(cat "$n/phy80211/name" 2>/dev/null)"
		has ethtool && ethtool -i "${n##*/}" 2>/dev/null | grep -E '^(driver|version|firmware-version|bus-info):'
	done

	echo "-- mt76 firmware (dmesg)"
	dmesg | grep -i -E 'mt7915|mt7916|mt76' | grep -i -E 'firmware|version|build time|rom patch' | tail -n 20
	echo "-- mt7916 firmware files"
	ls -l /lib/firmware/mediatek/mt7916* 2>/dev/null
	echo "-- morse firmware and driver"
	dmesg | grep -i morse | grep -i -E 'firmware|version|chip|board' | tail -n 20
	has modinfo && modinfo morse 2>/dev/null | grep -E '^(version|srcversion|vermagic|firmware):'
	ls -l /lib/firmware/morse 2>/dev/null
	if has morse_cli; then
		for i in $(ifaces_by_driver morse); do
			echo "morse_cli -i $i version:"
			morse_cli -i "$i" version 2>&1
		done
	fi

	echo "-- regulatory"
	iw reg get 2>&1
	echo "-- uci wireless country"
	uci -q show wireless | grep -E '\.(country|channel|band|htmode|disabled)='

	echo "-- per-phy summary: bands and mesh point"
	for p in /sys/class/ieee80211/*; do
		phy=${p##*/}
		info=$(iw phy "$phy" info 2>/dev/null)
		drv=$(basename "$(readlink "$p/device/driver" 2>/dev/null)")
		bands=$(echo "$info" | awk '
			/^[ \t]*Band [0-9]+:/ { b = $2; sub(":", "", b) }
			/MHz \[/ && b != "" && !/disabled/ {
				f = $2 + 0
				if (f < 3000) seen["2.4GHz"] = 1
				else if (f < 5950) seen["5GHz"] = 1
				else seen["6GHz"] = 1
			}
			END { for (k in seen) printf "%s ", k }')
		txbands=$(echo "$info" | awk '
			/MHz \[/ && !/disabled/ && !/[Nn]o IR/ {
				f = $2 + 0
				if (f < 3000) seen["2.4GHz"] = 1
				else if (f < 5950) seen["5GHz"] = 1
				else seen["6GHz"] = 1
			}
			END { for (k in seen) printf "%s ", k }')
		mesh=no
		if echo "$info" | grep -q '\* mesh point'; then mesh=yes; fi
		echo "PHY $phy driver=$drv enabled-bands=[ $bands] may-initiate-tx=[ $txbands] mesh-point=$mesh"
		case "$bands" in
			*6GHz*) [ "$mesh" = yes ] && echo "NOTE $phy advertises mesh point and has 6 GHz channels enabled: a capability flag, not a proven 6 GHz mesh link (see v1-radio-validation.md)" ;;
		esac
	done

	for p in /sys/class/ieee80211/*; do
		echo "-- iw phy ${p##*/} info"
		iw phy "${p##*/}" info 2>&1
	done
	echo "-- iw dev"
	iw dev 2>&1
	for i in $(iw dev 2>/dev/null | awk '$1 == "Interface" { print $2 }'); do
		echo "-- $i info"; iw dev "$i" info 2>&1
		echo "-- $i station dump"; iw dev "$i" station dump 2>&1
	done
}

# --- loops ---

restore_gpio() {
	# Back to the boot state of the V1 distroconfig: enables and hub reset
	# high, HaLow reset released (input, no pull). Never drive HALOW_RESET_N high.
	pinctrl set "$HALOW_PWR_EN" op dh
	pinctrl set "$WIFI_PWR_EN" op dh
	pinctrl set "$USB_HUB_RESET_N" op dh
	pinctrl set "$HALOW_RESET_N" ip pn
}

# One iteration of each test. Each prints "<device-seconds> <netdev-seconds>"
# on success and returns nonzero with a reason on stdout on failure.

it_wifi_pci_reset() {
	bdf=$(mt7916_bdf)
	[ -n "$bdf" ] || { echo "no-pci-device-before"; return 1; }
	[ -w "/sys/bus/pci/devices/$bdf/reset" ] || { echo "no-function-reset-for-$bdf"; return 1; }
	t0=$(now)
	echo 1 > "/sys/bus/pci/devices/$bdf/reset" || { echo "reset-write-failed"; return 1; }
	wait_for "$WIFI_PCI_TIMEOUT" have_pci || { echo "pci-timeout"; return 1; }
	td=$(since "$t0")
	wifi up >/dev/null 2>&1
	wait_for "$WIFI_NETDEV_TIMEOUT" have_wifi_netdev || { echo "netdev-timeout"; return 1; }
	echo "$td $(since "$t0")"
}

it_wifi_pci_rescan() {
	bdf=$(mt7916_bdf)
	[ -n "$bdf" ] || { echo "no-pci-device-before"; return 1; }
	echo 1 > "/sys/bus/pci/devices/$bdf/remove" || { echo "remove-failed"; return 1; }
	sleep "$OFF_S"
	t0=$(now)
	echo 1 > /sys/bus/pci/rescan
	wait_for "$WIFI_PCI_TIMEOUT" have_pci || { echo "pci-timeout"; return 1; }
	td=$(since "$t0")
	wifi up >/dev/null 2>&1
	wait_for "$WIFI_NETDEV_TIMEOUT" have_wifi_netdev || { echo "netdev-timeout"; return 1; }
	echo "$td $(since "$t0")"
}

it_halow_usb_reset() {
	dev=$(halow_usbdev) || { echo "no-halow-before"; return 1; }
	t0=$(now)
	if has usbreset; then
		usbreset "$(cat "$dev/busnum")/$(cat "$dev/devnum")" >/dev/null 2>&1 || { echo "usbreset-failed"; return 1; }
	else
		if ! echo 0 > "$dev/authorized"; then echo "authorized-toggle-failed"; return 1; fi
		sleep 1
		echo 1 > "$dev/authorized"
	fi
	wait_for "$HALOW_USB_TIMEOUT" have_path "$dev/idVendor" || { echo "usb-timeout"; return 1; }
	td=$(since "$t0")
	wifi up >/dev/null 2>&1
	wait_for "$HALOW_NETDEV_TIMEOUT" have_halow_netdev || { echo "netdev-timeout"; return 1; }
	echo "$td $(since "$t0")"
}

it_hub_reset() {
	dev=$(halow_usbdev) || { echo "no-halow-before"; return 1; }
	t0=$(now)
	pinctrl set "$USB_HUB_RESET_N" op dl
	sleep 1
	pinctrl set "$USB_HUB_RESET_N" op dh
	wait_for "$HALOW_USB_TIMEOUT" have_path "$dev/idVendor" || { echo "usb-timeout"; return 1; }
	td=$(since "$t0")
	wifi up >/dev/null 2>&1
	wait_for "$HALOW_NETDEV_TIMEOUT" have_halow_netdev || { echo "netdev-timeout"; return 1; }
	if [ -n "$vlm_before" ] && [ ! -e "$vlm_before/idVendor" ]; then
		echo "openvlm-did-not-return"; return 1
	fi
	echo "$td $(since "$t0")"
}

it_wifi_power() {
	bdf=$(mt7916_bdf)
	[ -n "$bdf" ] || { echo "no-pci-device-before"; return 1; }
	echo 1 > "/sys/bus/pci/devices/$bdf/remove" || { echo "remove-failed"; return 1; }
	pinctrl set "$WIFI_PWR_EN" op dl
	sleep "$OFF_S"
	t0=$(now)
	pinctrl set "$WIFI_PWR_EN" op dh
	sleep "$SETTLE_S"
	echo 1 > /sys/bus/pci/rescan
	wait_for "$WIFI_PCI_TIMEOUT" have_pci || { echo "pci-timeout"; return 1; }
	td=$(since "$t0")
	wifi up >/dev/null 2>&1
	wait_for "$WIFI_NETDEV_TIMEOUT" have_wifi_netdev || { echo "netdev-timeout"; return 1; }
	echo "$td $(since "$t0")"
}

it_halow_power() {
	dev=$(halow_usbdev) || { echo "no-halow-before"; return 1; }
	pinctrl set "$HALOW_RESET_N" op dl
	pinctrl set "$HALOW_PWR_EN" op dl
	sleep "$OFF_S"
	t0=$(now)
	pinctrl set "$HALOW_PWR_EN" op dh
	sleep "$SETTLE_S"
	pinctrl set "$HALOW_RESET_N" ip pn
	wait_for "$HALOW_USB_TIMEOUT" have_path "$dev/idVendor" || { echo "usb-timeout"; return 1; }
	td=$(since "$t0")
	wifi up >/dev/null 2>&1
	wait_for "$HALOW_NETDEV_TIMEOUT" have_halow_netdev || { echo "netdev-timeout"; return 1; }
	echo "$td $(since "$t0")"
}

peers() {
	c=0
	for i in $(ifaces_by_driver "$1"); do
		c=$((c + $(iw dev "$i" station dump 2>/dev/null | grep -c '^Station')))
	done
	echo "$c"
}
have_peer() { [ "$(peers "$1")" -gt 0 ]; }

loop() {
	test=$1 n=$2
	case "$n" in ''|*[!0-9]*) echo "iterations must be a number" >&2; exit 2 ;; esac
	case "$test" in
		wifi-pci-reset|wifi-pci-rescan|wifi-power) drv=mt7915e ;;
		halow-usb-reset|hub-reset|halow-power) drv=morse ;;
		*) echo "unknown test '$test'" >&2; exit 2 ;;
	esac
	case "$test" in
		hub-reset|wifi-power|halow-power)
			if [ "$ALLOW_GPIO" != 1 ]; then
				echo "$test drives GPIO. Set ALLOW_GPIO=1 only after GHO-21 verified polarity and no back-feed on this board." >&2
				exit 2
			fi
			has pinctrl || { echo "pinctrl missing (bcm27xx-utils)" >&2; exit 2; }
			trap restore_gpio EXIT INT TERM
			;;
	esac
	vlm_before=""
	for u in /sys/bus/usb/devices/*; do
		[ "$(cat "$u/idVendor" 2>/dev/null):$(cat "$u/idProduct" 2>/dev/null)" = "0d8c:0012" ] && vlm_before=$u
	done

	fn=it_$(echo "$test" | tr '-' '_')
	echo "== V1 radio loop $test x$n $(date -u '+%Y-%m-%dT%H:%M:%SZ') $(cat /tmp/sysinfo/board_name 2>/dev/null)"
	echo "== timeouts: off=${OFF_S}s settle=${SETTLE_S}s wifi pci/netdev=${WIFI_PCI_TIMEOUT}/${WIFI_NETDEV_TIMEOUT}s halow usb/netdev=${HALOW_USB_TIMEOUT}/${HALOW_NETDEV_TIMEOUT}s gap=${GAP_S}s"
	echo "result,iteration,test,device_s,netdev_s,peer_s,peers_before,peers_after,reason"
	pass=0 fail=0 i=1
	while [ "$i" -le "$n" ]; do
		pb=$(peers "$drv")
		t0=$(now)
		out=$($fn)
		st=$?
		ps=""
		if [ "$st" -eq 0 ] && [ "$pb" -gt 0 ]; then
			if wait_for "$PEER_TIMEOUT" have_peer "$drv"; then
				ps=$(since "$t0")
			else
				st=1 out="no-mesh-peer-after-${PEER_TIMEOUT}s"
			fi
		fi
		pa=$(peers "$drv")
		if [ "$st" -eq 0 ]; then
			pass=$((pass + 1))
			echo "PASS,$i,$test,${out%% *},${out#* },$ps,$pb,$pa,"
		else
			fail=$((fail + 1))
			echo "FAIL,$i,$test,,,,$pb,$pa,$out"
			dmesg | tail -n 15 | sed 's/^/      /'
			[ "$ALLOW_GPIO" = 1 ] && has pinctrl && restore_gpio
			case "$out" in *-before) echo "== radio missing before the test; stopping"; break ;; esac
		fi
		sleep "$GAP_S"
		i=$((i + 1))
	done
	echo "== $test: $pass pass, $fail fail of $n"
	[ "$fail" -eq 0 ]
}

case "$1" in
	capture) capture ;;
	loop) shift; loop "$@" ;;
	*)
		echo "usage: $0 capture | loop <test> <iterations>" >&2
		echo "tests: wifi-pci-reset wifi-pci-rescan halow-usb-reset hub-reset wifi-power halow-power" >&2
		exit 2
		;;
esac
