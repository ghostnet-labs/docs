# OpenMANET node project records

This folder holds the engineering records for the ghostnet-labs OpenMANET field node. It lives outside `docs/`, so the public OpenMANET website does not publish it. It replaces the Google Drive folder "Manet", which was retired on 2026-10-01.

**The project.** A compact, rugged, headless, battery-powered field mesh node built around a Raspberry Pi CM5 running OpenMANET (OpenWrt, 802.11s, batman-adv). Each node has a 900 MHz Wi-Fi HaLow radio, a 2.4/5 GHz Wi-Fi radio, GNSS, Ethernet and battery telemetry, and is managed entirely from an end-user device (EUD). The size reference is the Persistent Systems MPU5 (4.6 x 2.6 x 1.5 in, 117 x 67 x 38 mm).

**Two tracks.**
- Track A is an off-the-shelf proof of concept, tracked in the Linear project [OpenMANET POC](https://linear.app/ghostnet-labs/project/openmanet-poc-66239aa64a35).
- Track B is the custom V1 carrier and battery pack, tracked in [OpenMANET V1](https://linear.app/ghostnet-labs/project/openmanet-v1-1c6a34ebffa2).

The node's web interface work (one primary OpenMANET UI with LuCI behind Advanced, D-036) is tracked separately in [OpenMANET Unified UI](https://linear.app/ghostnet-labs/project/openmanet-unified-ui-937d7bff9664).
The current UI parity, configuration-ownership and proxy-path audit is [software/unified-ui-audit.md](software/unified-ui-audit.md) (GHO-67).

Data flows one way: Track A produces measurements and Track B consumes them. Track B must not lock any decision that Track A can settle.

## Expanded Maer capability contract

[requirements/maer-capabilities.md](requirements/maer-capabilities.md) owns the accepted expanded requirements (D-029 through D-032). [GHO-49](https://linear.app/ghostnet-labs/issue/GHO-49) publishes the handoff; [GHO-55](https://linear.app/ghostnet-labs/issue/GHO-55) reconciles V1 before freeze. The selected CM5 baseline above does not establish compliance with that expanded contract. The [planning study](poc/history-2026-10-04-maer-beast-poc.md) is historical provenance, not a purchasing record.

## One fact, one place

Every fact has exactly one owner. Everywhere else refers to it by ID or link and never restates its value.

| Kind of fact | Owner |
|---|---|
| Status, priority, who is doing what, next steps, blockers, open questions | Linear issues and project status updates |
| POC order quantities, vendors, prices, buy links, cart and delivery status | Linear doc [OpenMANET POC — Purchase BOM](https://linear.app/ghostnet-labs/document/openmanet-poc-purchase-bom-ff58aa264535) and [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36) |
| Expanded networking/controller, channel recovery, monitoring and coexistence requirements | [requirements/maer-capabilities.md](requirements/maer-capabilities.md) |
| Decisions (D-nnn) and retired or rejected items (R-nn) | [decisions.md](decisions.md) |
| Track A part selections and rationale (A-nn), mounting, selection risks | [poc/track-a.md](poc/track-a.md) |
| POC bench wiring, firmware revision, safety rules, arrival checks | [poc/bench-bom-and-topology.md](poc/bench-bom-and-topology.md) |
| Expanded candidate wiring, source audit and qualification procedures | [poc/maer-hardware-qualification.md](poc/maer-hardware-qualification.md) (candidate part identities remain in Track A; execution stays in Linear) |
| Track B selections (B-nn) and their status, power tree, PCB approach, Track A vs. B comparison (the Linear "BOM Baseline" doc only points here; BOM completion is [GHO-26](https://linear.app/ghostnet-labs/issue/GHO-26)) | [hardware/v1-selections.md](hardware/v1-selections.md) |
| Battery pack geometry (M-nn), design rules, CAD review gates | [hardware/v1-battery-pack.md](hardware/v1-battery-pack.md) |
| Track B CM5 physical pins, GPIO signal ownership, mux facts, and sequencing | [hardware/v1-pinout-and-sequencing.md](hardware/v1-pinout-and-sequencing.md) (canonical; GHO-9) |
| V1 carrier first-power procedure: inspection, resistance checks, bench current limits, sequence probes, boot capture, revision record and pass criteria (results stay on GHO-21) | [hardware/v1-first-power.md](hardware/v1-first-power.md) |
| Track B engineering detail: calculations, interfaces, placement, and validation plan | [hardware/v1-reference.md](hardware/v1-reference.md) (supporting; the registers above win; it links to the canonical pin/GPIO record) |
| Track B validation procedures, pass criteria and results template (results themselves go on [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23)) | [hardware/v1-validation-procedures.md](hardware/v1-validation-procedures.md) |
| V1 radio and dual-radio mesh validation procedure: radio capture, per-band mesh tests, reset and power-cycle loops, supported vs. unproven behavior (results stay on GHO-22) | [hardware/v1-radio-validation.md](hardware/v1-radio-validation.md) and its script `hardware/v1-radio-validate.sh` |
| CAD floorplan model and clearance check | firmware [`docs/hardware/v1-mechanical/`](https://github.com/ghostnet-labs/firmware/tree/24.10/docs/hardware/v1-mechanical) (a script, so it lives with code) |
| Unified UI origin, routing, sign-in behavior, recovery route and navigation (D-037) | [software/unified-ui-design.md](software/unified-ui-design.md) |
| Firmware source, board target, CI and build evidence | [ghostnet-labs/firmware](https://github.com/ghostnet-labs/firmware) and its PRs |
| History of the 2026-09-29 Track A options | [poc/history-2026-09-29.md](poc/history-2026-09-29.md) (historical, never authoritative) |

## Rules for every edit

These rules apply to people and agents alike.

1. **Change the owner first.** If work changes a requirement, selection, architecture or plan, update the owning file or issue in the table above. Then fix every place that refers to it, in the same PR.
2. **State it once.** Each selection, value and status lives in the row that owns it. Elsewhere, refer to it by ID (A-09, B-03, M-10, D-017, GHO-37). Prose explains; registers hold state.
3. **Changing a decision takes four steps in one PR.**
   1. Update the register row and its status.
   2. Add a row at the top of [decisions.md](decisions.md) with the date, what changed, why, and what it supersedes. Anything retired gets an R row.
   3. Search this folder for the old part number, name or value, and rewrite every statement that is now false.
   4. Update or close the Linear issue the decision settles, and link the PR from it.
4. **Delete stale text; do not annotate it.** Retired and rejected items live only in the Retired and rejected table. Leave no struck-through or "superseded" sentences in the body.
5. **Do not guess.** Never invent a pinout, part number, stock level, price or date. Mark the item Unverified and open a Linear issue for it. Write "not recorded" when a date is unknown.
6. **Do not resolve conflicts silently.** If two records disagree, open a Linear issue that names both, and ask the project owner. Do not pick a winner.
7. **Dates and IDs.** Use absolute dates (YYYY-MM-DD). IDs are permanent: never renumber or reuse one. A new item takes the next number in its prefix. A retired item moves to the Retired and rejected table and keeps its ID.
8. **Open questions are Linear issues.** Do not keep open-question lists in these files. A file may name the issue that tracks a gap.
9. **Finish with a consistency check.** Before merging, confirm that `poc/track-a.md`, `hardware/v1-selections.md`, `hardware/v1-battery-pack.md`, `hardware/v1-pinout-and-sequencing.md` and `decisions.md` still agree with one another and with the Linear issues they reference. Search for every changed signal name and GPIO number; maps outside the owning pinout record must link to it rather than restate allocations. Review against the current base branch before merge.

## Status words

Selected (chosen, not frozen), Candidate (leading option, not chosen), Open (undecided), Verified (confirmed from a source or a measurement; give the date), Unverified, Retired, Rejected. Battery geometry uses Locked, Target and CAD-verify.

## ID prefixes

| Prefix | Meaning | Owner |
|---|---|---|
| A-nn | Track A part (numbered like the retired Google BOM sheet rows) | [poc/track-a.md](poc/track-a.md) |
| B-nn | Track B selection | [hardware/v1-selections.md](hardware/v1-selections.md) |
| M-nn | Battery pack mechanical parameter | [hardware/v1-battery-pack.md](hardware/v1-battery-pack.md) |
| D-nnn | Decision | [decisions.md](decisions.md) |
| R-nn | Retired or rejected item | [decisions.md](decisions.md) |
| GHO-n | Open question, task or blocker | [Linear](https://linear.app/ghostnet-labs/team/GHO) |

The old Q-nn (open question) and C-nn (inconsistency) prefixes are closed. Older decisions still mention them, so this is where each one went on 2026-10-01:

| Former ID | Now |
|---|---|
| Q-01 CM5 image on hardware | [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28) |
| Q-02 802.11s mesh point on the AIW-170BQ | [GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37) |
| Q-03 Two HaLow radios on one host | [GHO-39](https://linear.app/ghostnet-labs/issue/GHO-39) |
| Q-04 Track A GPS placement | Closed by D-020 |
| Q-05 Two-node order | [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36) |
| Q-06 How the UPS feeds the Track A carrier | [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36), arrival check 12 |
| Q-07 Track B CAD assembly | [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7) |
| Q-08 AIW-170BQ M.2 pin table | [GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9) |
| Q-09 Open Track B parts (USB/Ethernet ESD, magnetics, GNSS protection and connector, enclosure) | [GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11) |
| Q-10 Hot-swap bridge energy | [GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38) |
| Q-11 Charging power-path integration | [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10) |
| Q-12 Battery pack design items | [GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8) |
| Q-13 Power budget | [GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) (measure), then [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10) (size) |
| Q-14 GNSS isolation | [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) (POC test), then [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12) |
| C-01 to C-06 | All resolved by D-016, D-017 and D-019 |

## External references

- [Raspberry Pi Compute Module documentation](https://www.raspberrypi.com/documentation/computers/compute-module.html)
- [OpenMANET hardware](https://openmanet.github.io/docs/hardware) and [networking](https://openmanet.github.io/docs/networking) documentation
- [Gateworks GW16170](https://www.gateworks.com/products/wireless-options/gw16170-mm8108-m20-802-11ah-halow-wifi-m2-card/)
- Part datasheets are listed in [hardware/v1-reference.md](hardware/v1-reference.md), section 32.

The retired Google Drive files stay in Drive with a "retired" banner that links here. Nothing in them is current.
