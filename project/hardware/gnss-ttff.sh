#!/bin/sh
# V1 GNSS time-to-first-fix and PPS logger (GHO-23, tests GN-1 to GN-3).
#
# Usage, on the node as root:
#   sh gnss-ttff.sh [-m cold|warm|hot|none] [-n runs] [-t timeout_s] [-p pps_s] > gnss-<test>.csv
#
#   -m  receiver restart before each run (default cold). cold/warm/hot send
#       COLDBOOT/WARMBOOT/HOTBOOT with gpsd's ubxtool; "none" measures from the
#       moment the script starts (use it right after power-on).
#   -n  number of TTFF runs (default 1)
#   -t  per-run timeout in seconds (default 300); a timeout is a FAIL row
#   -p  after the TTFF runs, count PPS pulses on /dev/pps0 for this many
#       seconds with ppstest (default 0 = skip)
#
# One CSV row per run:
#   utc        ISO 8601 UTC time the run started
#   kind       ttff or pps
#   mode       cold, warm, hot or none (ttff); the PPS device (pps)
#   run        run number
#   result     PASS (3D fix / pulses seen), FAIL (timeout / no pulses) or ERROR
#   ttff_s     seconds from restart to the first gpsd TPV with mode 3
#   sats_used  satellites used in the first fix (gpsd SKY uSat), or blank
#   pulses     PPS assert events seen (pps rows)
#   seq_gaps   missing PPS sequence numbers (pps rows)
#   max_dev_us largest deviation of an assert interval from 1 s, in µs (pps rows)
# Pass criteria are in v1-validation-procedures.md, not here.
# Needs gpsd and gpspipe; ubxtool for cold/warm/hot; ppstest for -p.
# It changes no settings beyond the requested receiver restart.

mode=cold runs=1 tmo=300 pps=0
while getopts m:n:t:p: o; do
	case $o in
	m) mode=$OPTARG ;;
	n) runs=$OPTARG ;;
	t) tmo=$OPTARG ;;
	p) pps=$OPTARG ;;
	*) sed -n '2,13p' "$0" >&2; exit 2 ;;
	esac
done

case $mode in
cold) boot=COLDBOOT ;; warm) boot=WARMBOOT ;; hot) boot=HOTBOOT ;; none) boot="" ;;
*) echo "unknown mode: $mode" >&2; exit 2 ;;
esac

has() { command -v "$1" >/dev/null 2>&1; }
now() { read -r up _ < /proc/uptime; echo "$up"; }
utc() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

has gpspipe || { echo "gpspipe not found (install gpsd-clients)" >&2; exit 2; }
[ -z "$boot" ] || has ubxtool || { echo "ubxtool not found; use -m none and power-cycle the receiver" >&2; exit 2; }

echo "utc,kind,mode,run,result,ttff_s,sats_used,pulses,seq_gaps,max_dev_us"

# Wait for the first 3D fix after a restart. A restart first drops the fix, so
# TPV reports are ignored until gpsd shows mode < 3, or 3 s have passed (hot starts
# can keep the fix through the restart).
ttff_run() {
	n=$1
	start_utc=$(utc)
	t0=$(now)
	if [ -n "$boot" ] && ! ubxtool -p "$boot" >/dev/null 2>&1; then
		echo "$start_utc,ttff,$mode,$n,ERROR,,,,,"
		return
	fi
	timeout "$tmo" gpspipe -w 2>/dev/null | awk -v t0="$t0" '
		function up(   l, f) { getline l < "/proc/uptime"; close("/proc/uptime"); split(l, f, " "); return f[1] }
		/"class":"SKY"/ && match($0, /"uSat":[0-9]+/) { sats = substr($0, RSTART + 7, RLENGTH - 7) }
		/"class":"TPV"/ {
			m = 0; if (match($0, /"mode":[0-9]/)) m = substr($0, RSTART + 7, 1) + 0
			t = up()
			if (m < 3) armed = 1
			if (!armed && t - t0 >= 3) armed = 1
			if (armed && m == 3) { printf "%.1f,%s\n", t - t0, sats; found = 1; exit }
		}
		END { if (!found) print "" }' > /tmp/gnss-ttff.$$
	res=$(cat /tmp/gnss-ttff.$$); rm -f /tmp/gnss-ttff.$$
	if [ -n "$res" ]; then
		echo "$start_utc,ttff,$mode,$n,PASS,$res,,,"
	else
		echo "$start_utc,ttff,$mode,$n,FAIL,,,,,"
	fi
}

i=1
while [ "$i" -le "$runs" ]; do
	ttff_run "$i"
	i=$((i + 1))
	# Let the receiver settle between runs so the next restart starts from a fix.
	[ "$i" -le "$runs" ] && sleep 30
done

if [ "$pps" -gt 0 ]; then
	start_utc=$(utc)
	if ! has ppstest; then
		echo "$start_utc,pps,/dev/pps0,1,ERROR,,,,,"
		exit 0
	fi
	# ppstest lines: "source 0 - assert 1700000000.000000123, sequence: 42 - clear ...".
	# Split seconds and nanoseconds so awk's doubles keep nanosecond resolution.
	timeout "$pps" ppstest /dev/pps0 2>/dev/null | awk -v u="$start_utc" '
		/assert/ {
			if (!match($0, /assert [0-9]+\.[0-9]+/)) next
			split(substr($0, RSTART + 7, RLENGTH - 7), ts, ".")
			if (!match($0, /sequence: [0-9]+/)) next
			seq = substr($0, RSTART + 10, RLENGTH - 10) + 0
			if (n > 0) {
				if (seq > pseq + 1) gaps += seq - pseq - 1
				d = (ts[1] - ps) * 1e9 + (ts[2] - pn)
				if (seq == pseq + 1) { dev = d - 1e9; if (dev < 0) dev = -dev; if (dev > max) max = dev }
			}
			n++; pseq = seq; ps = ts[1]; pn = ts[2]
		}
		END {
			r = (n > 0) ? "PASS" : "FAIL"
			printf "%s,pps,/dev/pps0,1,%s,,,%d,%d,%.3f\n", u, r, n, gaps, max / 1000
		}'
fi
