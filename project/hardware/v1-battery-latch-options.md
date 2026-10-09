# V1 battery pack latch options (replacement for B-13)

**Owner:** [GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8). This file supports the B-13 pack-latch question in that issue.
**Status:** Research proposal, 2026-10-09. Nothing here changes a register. B-13 in [v1-selections.md](v1-selections.md), D-012 in [../decisions.md](../decisions.md) and M-20 in [v1-battery-pack.md](v1-battery-pack.md) stay as they are until the project owner decides. Every part below is a **Candidate**, not Selected.

## Why B-13 needs a replacement

The first CAD gate pass ([v1-battery-pack-gates.md on branch `gho8-pack-gates`](https://github.com/ghostnet-labs/docs/blob/gho8-pack-gates/project/hardware/v1-battery-pack-gates.md), gates 1 and 4) found two problems with the Southco C3-99-107-055 grabber catch:

1. **Envelope.** The C3 family catch body is about 26.6 x 43 x 17 mm, taken from the family drawing because the C3-99-107-055 drawing could not be retrieved. That body cannot fit the 7 mm X span of the M-20 latch zone (X 134 to 141) in any orientation.
2. **Retention.** B-13 is a 5 lbf-class (about 22 N) catch, and it releases by pulling rather than by a positive lock. The gate-4 moment balance says the latch must hold about 24 to 41 N of gasket and probe preload before any shock load.

The design rule in v1-battery-pack.md also calls for a positive, recessed, glove-operable latch with no tools. If one centered latch compresses the seal unevenly, it calls for two symmetric catalog catches instead.

## Requirements used for screening

| Requirement | Source | Screening value |
|---|---|---|
| Fit | M-20, M-21; the end wall is X 141 to 145 (M-03) | Fits inside the 145 x 74 mm frame, or in a zone justified with dimensions below |
| Retention | Gates record, gate 4 | At least 41 N, with clear margin. Rated load of about 100 N or more preferred. |
| Seating | Latch design rule | Pulls the pack onto the M-17 hard stops. It must not set the probe stroke and must not rely on latch elasticity for working height. |
| Operation | Attachment design rule | Tool-free, or a captive tool; glove-operable; recessed against accidental release |
| Sourcing | Sourcing design rule | Catalog part, orderable now in small quantities from an authorized distributor |
| Environment | D-028 | Works across −17.8 to +43.3 °C ambient |

## Load check, by latch position

The gate-4 estimate puts the latch at X 137.5 and needs 24 to 41 N there. In that moment balance, the gasket and probes act at X 117 and the hooks at X 3.5. Working back gives a combined gasket-plus-probe load of about 28 to 48 N. Moving the latch changes the force it needs:

| Latch line of action | Arm from the hooks | Latch force needed (total) |
|---|---|---|
| X 137.5 (M-20 today) | 134 mm | 24 to 41 N |
| X 145 end face (options A, B and C) | 141.5 mm | 23 to 39 N |
| X 84.5, in the M-22 spare zone (option D) | 81 mm | 40 to 68 N |

These are first-order estimates. They inherit the gate-4 gasket-load assumption, which is a rough reading of Parker ORD 5700 Fig. 2-4, and they include no shock or drop load.

## Options

All four candidates are Southco catalog parts. Load ratings and dimensions come from Southco catalog pages, read as distributor-hosted PDF copies on marek.eu on 2026-10-09, because southco.com refused scripted access. The price and stock snapshot comes from the Findchips aggregator on 2026-10-09. Findchips returned results only intermittently, and it is not the distributor's own page. **All price and stock figures are Unverified.**

### Summary table

| | A. One small draw latch | B. Two small draw latches (recommended) | C. Miniature push-to-close paddle latch | D. Micro rotary latch in the spare zone |
|---|---|---|---|---|
| Part number (latch) | Southco 97-30-160-12 (stainless steel) | 2 x Southco 97-30-160-12 | Southco 64-01-10 | Southco R4-05-21-405-10 (single stage, hand actuation, 8-32 mounting, steel) |
| Mating part | Keeper 97-37-103-24 (concealed 2-hole, stainless) | 2 x keeper 97-37-103-24 | Radio-side catch lip (molded; grip 3.2 ±0.2 mm) | Striker bolt R4-90-0521-10 (adjustable, M5) or molded striker R4-0-61336 |
| Type | Over-center draw latch | Over-center draw latch, symmetric pair | Spring slide behind a frame lip; lift paddle to release | Rotary claw on a striker; push to close |
| Datasheet | [97 Draw Latch catalog page (marek.eu copy)](https://www.marek.eu/katalog-obrazku/produkt-8375/19129-97-en.pdf), p. 282 | same | [64 Push-to-Close Latch catalog page (marek.eu copy)](https://www.marek.eu/katalog-obrazku/produkt-8258/18901-64-en.pdf), p. 244 | [R4 Rotary Latch catalog pages (marek.eu copy)](https://www.marek.eu/katalog-obrazku/produkt-27975/66617-r4-r-en.pdf), p. 255A |
| Product photo | Photo at the top of p. 282 of the datasheet link; [Southco product page](https://southco.com/en_us_int/97-30-160-12) (not fetched) | same | Photo at the top of p. 244 of the datasheet link; [Southco product page](https://southco.com/en_us_int/64-01-10) (not fetched) | Photo at the top of p. 255A of the datasheet link; [Southco product page](https://southco.com/en_us_int/r4-05-21-405-10) (not fetched) |
| Envelope (catalog) | Latch 27.4 long x 12.6 wide x 7.9 high, closed. Keeper 14.3 x 10.7 x 3.6. M3 screws, Ø3.3 holes. | Two of the A envelope | Flange 43 x 28 x 0.9; about 8 mm behind the panel, plus the M4 screw; the slide projects 11 mm past the flange and is 13 mm wide. Panel cutout 39 x 24.5. Panel 1.6 mm max at the latch. | Body 46 x 21.2 x 10 behind the panel; hand lever 12.7 mm. Striker bolt 28.2 long. |
| Rated force (catalog) | Clamping force 135 N (30 lbf) | 270 N total clamping force (2 x 135 N) | Maximum working load 90 N (20 lbf) | Average ultimate load 2600 N (590 lbf) |
| Margin against the need at its position | 3.5 x (135 / 39 N) | 6.9 x (270 / 39 N) | 2.3 x (90 / 39 N) | 38 x (2600 / 68 N) on ultimate load. No working load published. |
| Seats on the hard stops? | Yes: the over-center draw pulls the pack up against the hard stops | Yes, and evenly in Y | **No.** The slide catches at a fixed height with ±0.2 mm grip tolerance, so the gasket pushes the pack down onto the slide. The latch, not the hard stops, would set the face gap. | Only if the striker bolt is set to preload the pack against the hard stops. The integrated bumper takes up the play. |
| Operation | Lift the recessed lever tab. Tool-free. | same, twice | Push to close; lift the paddle to open. Tool-free. | Push to close; the release lever must be reached through a side opening (or with a Southco cable, not chosen). Tool-free. |
| Temperature | All-metal (stainless) | All-metal | Nylon slide rated −18 to 100 °C. The D-028 low end is −17.8 °C, so there is no margin. | Steel |
| Seal relationship | Outside the gasket, on the pack's outer shell. Screws must go into blind inserts that do not open the sealed pack enclosure. | same | Outside the gasket, but the 39 x 24.5 mm panel cut-out opens the pack shell. The latch body needs its own closed pocket. | Outside the gasket, but the striker enters the pack through a slot in the interface plate, and the latch body sits in a pocket in the M-22 zone. That pocket must be sealed off from the cell enclosure. |
| Price and stock snapshot (2026-10-09, Unverified) | 97-30-160-12: DB Roberts (authorized), 3,909 in stock, $9.40 (1), $7.47 (100). 97-37-103-24: Bisco 19 in stock, price not shown; DB Roberts 0 (RFQ). | Same parts, two sets. Keeper stock (19 at Bisco) covers about nine packs. | Not obtained. Findchips returned no exact match. | R4-05-21-405-10: Bisco 140 in stock, price not shown; DB Roberts 0 (RFQ). R4-90-0521-10: Bisco 74. R4-0-61336: Bisco 312. |
| Change to M-20 | Moves the latch from the top-face zone (X 134 to 141, near Y 37) to an end-face pocket, X 136 to 145, Y about 30 to 44, Z 0 to about 16 on the pack (all assumed). The pocket overlaps the gland's Y span, so it also needs gates-record gate-1 option 1 (shorter gasket on the latch side). | Two end-face pockets at Y about 5 to 21 and 53 to 69 (in line with the M-19 hooks at Y 14 and 60), X 136 to 145, Z 0 to about 16 (all assumed). They sit outside the gland's Y span (Y 22.55 to 51.45), leaving about 1.5 mm of wall. | End-face pocket, X about 137 to 145, Y about 23 to 51, Z 0 to about 43 (nearly the full 46 mm height), plus a radio-side catch slot about 13 x 11 mm. Needs the end wall thinned to 1.6 mm at the latch. | The latch leaves M-20 entirely and moves to M-22 (X 74 to 95). The body's 21.2 mm fits the 21 mm zone only with about 0.2 mm interference (CAD-verify). The 46 mm length runs along Y. M-20 is freed, which also clears the gland overlap. |
| Change to pack length | None | None | None | None |
| Change to the radio side | Two M3 holes for the keeper on the radio end face, Z 0 to about 17 above the parting line. The keeper stands 3.6 mm proud, or sits in a shallow recess. | Two keepers | A catch slot with a 3.2 mm-grip lip in the radio bottom, near X 141 to 145 | A striker that protrudes about 26 mm below the radio bottom plate at X about 84.5 |

### Option notes

**A. One Southco 97-30 draw latch.** This is the smallest positive latch found with a published force. An over-center draw latch suits a hook-and-pivot pack: the user hooks the pack, swings it closed, hooks the latch spring over the keeper and pushes the lever down, and the latch pulls the pack onto the hard stops. A single centered latch is symmetric in Y, but its pocket at Y 30 to 44 collides with the gasket gland unless the gasket is shortened as in gate-1 option 1. It also leaves the pack free to rock about X under a side drop.

**B. Two Southco 97-30 draw latches, one in line with each hook.** This is the design rule's "two symmetric catalog catches", using the same part as option A. Each latch carries only about 11 to 20 N of the static preload against its 135 N clamping force. One latch still holds the full static preload if the other is left open. The two pockets sit outside the gasket's Y span, so this option does not need the gasket shortened for latch clearance. The gland still needs to come out of the old M-20 top-face zone, which becomes free. The hooks and latches share the same two Y lines, which gives a straight load path down each sidewall (M-03).

**C. Southco 64-01-10 miniature push-to-close paddle latch.** It latches automatically, and its flush paddle is the best match for "recessed against accidental activation". Two problems keep it from being recommended. First, it catches at a fixed height rather than drawing the pack down, which conflicts with the rule that the hard stops, not the latch, set the face gap. Second, its nylon slide is rated only to −18 °C. Its 90 N working load also leaves the least margin of the four options.

**D. Southco R4-05 micro rotary latch in the M-22 spare zone.** This option has the most strength by far, and it frees M-20 completely. However, at X 84.5 the latch sits inboard of the gasket, so it needs about 1.7 x the force of an end latch. Under shock the end of the pack beyond X 85 is held only by its own stiffness. The release lever has to be brought out through the sidewall or the pack bottom, which needs another sealed opening or a cable. It is also the heaviest integration job of the four options.

### Considered and rejected

| Candidate | Why it was rejected |
|---|---|
| Southco C3 grabber catch (B-13 today) | About 22 N, below the 24 to 41 N need. The family body is about 26.6 x 43 x 17 mm. It releases by pulling, not by a positive lock (gates record). |
| Southco E3 vise-action compression latch (smallest version) | A distributor listing for E3-19-15 gives 47.5 x 29 x 64 mm. It mounts through a panel and needs a 64 mm-deep body, which is far beyond the 46 mm pack height at the latch end. Its 6.4 mm pull-up is also more travel than the hard-stop design wants. |
| Quarter-turn captive fasteners (Southco DZUS family) | They need a receptacle on the radio and access to the head along the fastening axis (Z). At the latch end that means a sealed tube through the full 46 mm pack height, or an external flange that adds length. No catalog stud long enough was identified. |
| Captive thumbscrews (PEM PF11 family) | The same access problem: the axis is Z, through 46 mm of pack. The PF11 family is made for clinching into thin metal panels, and the catalog only listed M3 and M3.5 metric sizes and 8-32 for the plastic-cap PF11PM. Several turns per fit is also slow in the field. The PEM data sheet (Mouser-hosted) could not be fetched, so pull-out data was not checked. |
| Molded cantilever snap with a separate lock slide | Not a catalog part: it needs custom tooling, and its retention is unknown until tested. The design rule bars cutting tooling around an estimated latch envelope. It could be revisited after V0 if the draw latches prove awkward. |
| Southco C7 soft (rubber) draw latch | Southco publishes only a 49 N steady clamp for the C7-10 marine part (per a search summary; not read from a data sheet). That leaves almost no margin, and the part is sized for marine hatches. |
| Southco 97-50 medium draw latch | A larger version of options A and B: 310 N light-duty clamping force, but about 46 to 48 mm long and 23.8 mm wide. It is only worth considering if the 97-30 proves too weak in test. |

## Recommendation

**Option B:** two Southco 97-30-160-12 stainless over-center draw latches with 97-37-103-24 concealed two-hole keepers. Mount the latches in end-face pockets on the pack at about Y 14 and Y 60, in line with the hooks, and the keepers on the radio end face.

Reasons:

- It is the only option that meets every screening line: it fits, gives about 6.9 x static margin, and is positive, tool-free and catalog-stocked. It is also all-metal across the D-028 range.
- The draw action seats the pack on the hard stops, as the latch design rule requires.
- It is the symmetric two-catch arrangement the design rule names, so it settles the uneven-compression question up front instead of waiting for CAD.
- The pockets keep out of the gasket's Y span, and the pack length stays at 145 mm.

What it changes, if adopted (each is a register change for the project owner, not made here):

- B-13 and D-012 would be superseded (a new D row, and an R row for the C3).
- M-20 would be redefined from "X 134 to 141 near Y 37" to two end-face latch pockets.
- The radio enclosure (GHO-11) gains two keeper mounting areas on its end face.

The gasket gland can then use the freed top-face zone near X 134 to 141. Gate-1 option 1 may no longer be needed, which the model should confirm.

Before release, check these items in CAD and on the bench:

- **Keeper and latch geometry.** The keeper position against the latch spring, which the catalog shows as 0.9 mm (.035 in) door/frame separation; how far the pack-side latch extends below the parting line and the keeper above it (about 16 and 17 mm, estimated); and glove access to the lever tab in a 16 mm-wide pocket.
- **Accidental release.** Whether the lever stays closed under drop and brush snag. The 97-30 has no secondary catch, unlike the 97-50.

## Verification status

**Unverified:**

- **Price and stock.** Every price and stock figure came from Findchips, an aggregator, on 2026-10-09. DigiKey, Mouser, Newark, RS Components, Octopart and the DB Roberts and Bisco product pages all refused scripted access or returned bot pages. No figure was read from a distributor's own page.
- **Option C stock.** No price or stock was obtained for the 64-01-10.
- **Part-number details.** Stock for the R4-05 stainless metric variant was not checked, and the existence of the builder code R4-05-22-405-20 is unconfirmed.
- **Product photo pages.** The southco.com product-photo links follow Southco's URL pattern and were not fetched: southco.com returned 403 or a DNS failure. The photos in the catalog PDFs were seen.
- **Pocket and keeper geometry.** Every pocket position and size, and the Z extents of the latch and keeper, are assumptions scaled from the catalog drawings. They have not been modeled in `pack.py`.
- **Required latch force.** It inherits the gate-4 gasket-load assumption, and no shock load is included.
- **C7 clamp figure.** Taken from a search summary, not from a data sheet.
- **E3-19-15 envelope.** Taken from an RS listing title, not from a data sheet.
- **PEM PF11 range.** The metric sizes and plastic-cap thread came from a search summary of the PEM catalog, not from the catalog itself.
- **Rating type.** Southco's 97-30 figure is a clamping force, not an ultimate or pull-off load. No ultimate load is published for the 97-30. The R4 figure is an average ultimate load, not a working load.

**Read from catalog pages (marek.eu copies of Southco pages, 2026-10-09):**

- the 97-30 dimensions and its 135 N clamping force
- the 97-50 dimensions and its clamping forces
- the 64-01-10 dimensions, its 90 N working load and its −18 to 100 °C temperature range
- the R4-05 dimensions and its 2600 N average ultimate load

**Could not fetch:**

- southco.com product and handbook pages
- the C3-99-107-055 drawing (still missing, as recorded in the gates file)
- the PEM PF captive-screw data sheet on Mouser
- distributor product pages, as listed above
