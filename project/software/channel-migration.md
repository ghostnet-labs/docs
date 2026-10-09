# Channel migration and returning-node recovery

**Owner:** [GHO-52](https://linear.app/ghostnet-labs/issue/GHO-52) (implement authenticated channel migration and absent-node rediscovery)  
**Status:** Proposal, 2026-10-09. The software is implemented and simulation-tested in openmanetd `internal/chanmig` ([openmanetd PR #31](https://github.com/ghostnet-labs/openmanetd/pull/31)). It is not yet wired to alfred, mgmt or an RPC, and it does not tune a real radio. No RF behavior is verified.

This file owns the protocol design for coordinated channel changes and for nodes that missed them: the plan message, how it is authenticated, the staged switch, the rediscovery state machine, the partition/merge rule, the recovery bound and the default timers. It does not own the requirements. Those are in [requirements/maer-capabilities.md §3](../requirements/maer-capabilities.md#3-channel-migration-and-returning-node-recovery). Mesh evidence is [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31). Exact driver channel-switch and dual-HaLow behavior is [GHO-39](https://linear.app/ghostnet-labs/issue/GHO-39). Path selection is the adaptive controller ([GHO-51](https://linear.app/ghostnet-labs/issue/GHO-51)); this protocol only moves channels when the controller or an operator asks it to.

Where something here disagrees with the code, the code's tests show what actually runs, and this file is fixed in the same PR.

## 1. Model

A node has up to three radios, one per band: HaLow, 2.4 GHz and 5 GHz. Each radio has one current **assignment**: a channel number plus a width. HaLow allows 1, 2, 4 or 8 MHz; 2.4 GHz allows 20 or 40 MHz; 5 GHz allows 20, 40, 80 or 160 MHz.

Every node keeps this information offline, provisioned at setup next to the mesh credentials:

| Item | Use |
|---|---|
| Plan-authority public key(s) | Verify plans (section 3) |
| Plan-authority private key | Only on nodes provisioned as coordinators |
| Mesh ID | Binds plans to this mesh |
| Per band: initial assignment | Version-0 plan before any signed plan exists |
| Per band: rendezvous list | Short list of regroup channels used for parking during search |
| Per band: allowed list | Every channel/width a plan may use; the search sweep |
| Accepted plans | The current plan plus up to four older ones, persisted across power loss |

Because every plan must stay inside the allowed list, a node that sweeps that list will always pass the mesh's channel on any band it can reach. That is what makes the search bounded. A fixed rescue channel would not be enough on its own, since it can be jammed too.

## 2. Plan message

A plan is versioned and covers the whole mesh:

| Field | Meaning |
|---|---|
| Mesh ID | 64-bit mesh identifier |
| Version | Increases by one per plan, mesh-wide. 0 is reserved for the provisioned initial assignments |
| Signer ID | Node ID of the issuing coordinator |
| IssuedAt | Signer's time when created (ms) |
| ActivateAt | Not-before switch time (ms). At most 10 min after IssuedAt |
| Stagger | Gap between successive changed bands (ms, at most 60 s) |
| Assignments | At most one per band, sorted by band |

**Canonical encoding.** The plan is encoded big-endian with a fixed layout: magic `OMCP`, format byte `1`, mesh ID, version, signer ID, IssuedAt, ActivateAt, stagger, count, then one `band | channel | width` record per assignment. A plan with three bands is 65 bytes. Decoding rejects trailing bytes, unknown formats, unsorted or duplicate bands and invalid widths. Anything that decodes therefore re-encodes to the same bytes, and the signature covers exactly what was parsed.

**Wire messages.** There are two:

- **Advert:** sender ID, then either the newest plan the sender holds (raw bytes plus a 64-byte signature) or a "no plan" flag. Adverts are both the migration announcement and the periodic proof of where the mesh is. Every node sends one on each working band once per AdvertInterval, and again immediately after accepting a new plan, so a new plan floods the mesh.
- **Ack:** sender ID, plan version and signer ID. A node sends it when it accepts a plan whose activation is still in the future. Each node relays an ack the first time it sees it, so acks reach a coordinator several hops away.

## 3. Authentication and replay protection

**Default: Ed25519 signatures over the canonical plan bytes.** At setup, a mesh-wide plan-authority key pair is generated. Every node gets the public key. Only nodes provisioned as coordinators get the private key. A node accepts a plan only if one of its trusted public keys verifies the signature, the mesh ID matches and local policy holds (section 4).

**Why not HMAC with the shared mesh key.** An HMAC can only be checked by someone who holds its key, and anyone who can check it can also forge it. Today every node holds the mesh passphrase. So does every EUD that scanned the mesh-join QR code, and alfred payloads are already protected with a key derived from that passphrase (openmanetd `internal/security/payload_codec.go`). With HMAC, a lost phone or a captured leaf node could retune the whole mesh. With Ed25519, verifying needs only the public key, so ordinary nodes and EUDs cannot issue plans.

The costs are small. Plans are rare. Signatures are 64 bytes. Verification is a few milliseconds even on slow hosts, and byte-identical repeats of the current plan are not re-verified. The verifier accepts a list of keys, so the authority key can be rotated without a flag day.

**Membership on the wire.** Adverts and acks travel inside the existing alfred payload codec, which authenticates mesh membership and rejects payloads outside its replay window. The Ed25519 check is a second, independent gate on the plan itself. An ack carries no signature: a forged ack can at worst stop the coordinator from aborting a plan, and the plan's own verify-and-fallback still protects each band.

**Replay protection:**

- **Monotonic version.** A node accepts a plan only if it ranks above its current plan (section 6). The current plan is persisted, so a replayed older plan is rejected after a reboot too. A stale plan is counted and answered with the node's current plan.
- **Mesh ID** stops a plan from being replayed into another mesh.
- **Not-before ActivateAt, bounded lead.** No node switches before ActivateAt, and a plan whose lead is longer than MaxLead is rejected. A captured plan cannot be held back and used to schedule a switch far in the future.
- **Residual risk.** A node whose storage was wiped has no version to compare against. An attacker could feed it an old, genuinely signed plan. That only sends this one node to an older valid channel set. The node loses its peers and searches, and the next advert it hears carries the higher version. The cost is one recovery, never a mesh-wide change.

## 4. Staged switch

1. **Announce.** A coordinator builds the plan with version = current + 1, ActivateAt = now + lead (default 30 s) and stagger 5 s, signs it and accepts it locally. Adverts flood it through the mesh. The coordinator should change at most two of the three bands in one plan, so that an unchanged band keeps the partitions of a failed switch reachable. The code does not enforce this; it is coordinator policy.
2. **Accept.** Every node verifies the plan and checks local policy: lead at most MaxLead, and every assignment for a band it has inside that band's allowed list. It then persists the plan, refloods it, sends an ack and schedules the switch.
3. **Ack collection.** At ActivateAt − AbortMargin (5 s), the coordinator compares the acks it has received with the peers it heard in the last PeerWindow. If half or fewer of those peers acked, it issues a **revert plan**: version + 1, the previous plan's assignments, the same ActivateAt. A node that got the revert stays where it is. A node that only got the original switches, finds no one, and falls back to the previous assignment, which is the revert's channel.
4. **Switch at T.** Changed bands switch one at a time, in band order (HaLow, 2.4 GHz, 5 GHz), at T, T + stagger, and so on. Unchanged bands keep running, so a working path stays up while each moved band is checked ("make before break"). A plan that arrives after T is applied at once, with the same stagger starting from when it arrived.
5. **Verify.** If a band heard a peer in the PeerWindow before switching, it must hear a peer on its new assignment within VerifyBound (8 s).
6. **Fall back.** If it hears no one, it returns to its previous assignment for FallbackBound (8 s). If peers answer there, the band stays on the previous assignment (the whole mesh failed to move). If not, it returns to the plan's assignment. A band that sits off its plan with no peers for PeerLossTimeout is retuned to the plan.
7. **Coordinator loss.** A plan is complete once it is announced, and every holder switches at T without further messages. If the coordinator disappears after announcing, the plan still completes. If it disappears before the abort check, the plan simply cannot be aborted. Any other key holder can issue the next plan.
8. **Clock loss.** A node whose clock is not disciplined (no GNSS or mesh time) switches at receipt time + (ActivateAt − IssuedAt), not at the absolute ActivateAt. The default lead of 30 s leaves room for a few seconds of skew between disciplined nodes.

## 5. Rediscovery state machine

Rediscovery starts in two cases: a node hears no peer on any band for PeerLossTimeout (20 s), or a node has just booted and hears no peer within ColdBootGrace (10 s) on its last-known plan. A node that missed one announcement, missed several, or was powered off ends up in the same place.

```
         boot                       peer heard
 ┌──────────────┐  ──────────────────────────────────▶ ┌────────┐
 │ BOOTING      │                                      │ STABLE │◀──┐
 │ last-known   │  grace expired      no peers for     └────────┘   │
 └──────────────┘ ─────────┐        PeerLossTimeout ───────┘        │
                           ▼                                        │
                    ┌────────────┐  epoch end, coin=park   ┌──────┐ │
                    │ SEEK epoch │ ──────────────────────▶ │ PARK │ │
                    │ dwell on   │ ◀────────────────────── │ 2 ep │ │
                    │ each entry │        park over        └──────┘ │
                    └────────────┘                                  │
                      │ authenticated advert or ack heard ──────────┘
```

**Candidate list.** Each radio has its own ordered, de-duplicated list, and all radios search in parallel. If only HaLow can reach the mesh, HaLow finds it without waiting for Wi-Fi. A failed radio is skipped and retried every RadioRetry (10 s). The list order is:

1. the last-known plan's assignment;
2. older accepted plans, newest first (up to four);
3. the provisioned initial assignment;
4. the rendezvous list;
5. the allowed list.

**Seek.** For each list step, the radio tunes to the entry and listens for one Dwell (3 s). Dwell is at least two AdvertIntervals, so a stable neighbour on that channel is heard. One epoch E is the longest list length × Dwell.

**Park.** At the end of a seek epoch, a per-node deterministic coin flip decides whether the node parks. Parking means every radio sits on a rendezvous entry for 2E; successive parks rotate through the list, so a jammed rendezvous channel is skipped next time. A node never parks twice in a row.

Parking exists for the case where every node is searching, such as after a mesh-wide power loss. A parked node is a fixed target that a seeking node will reach within one epoch. A mesh that is running normally never parks, so the search finds it on its own channel.

**Exit.** The first advert or ack heard on any band ends the search. If the advert's plan ranks higher, it is accepted. The band that heard the peer stays on that channel, unless the peer holds an older plan and is about to move. Every other band tunes to the current plan's assignment. The node then floods its own plan, so a peer that is behind catches up.

## 6. Partition and merge

Two partitions can issue different plans with the same version. Nodes rank any two valid plans by:

1. higher version;
2. then higher signer ID;
3. then the larger canonical bytes. This happens only if one signer issued two different plans with the same version, which is a fault; it is logged and still resolves the same way on every node.

When partitions touch again on any shared channel, the winning plan floods across and the losing side applies it at once (late plan, section 4 step 4). Leaving at least one band unchanged per plan (section 4 step 1) keeps a shared channel available for this. If every band diverged, partitions merge only when a node that lost its peers finds the other side through rediscovery and carries the winning plan back. A coordinator issuing the next plan uses the highest version it has seen plus one.

## 7. Recovery bound

Take a node whose mesh is stable on a channel in its search list, on a band it can reach. Once RF coverage returns, it rejoins within

**B = PeerLossTimeout + 4 × E + Dwell**, where E = longest candidate list × Dwell.

The worst case: one seek epoch has just passed the right entry, then a 2E park follows, then the next seek reaches the entry within E. The PeerLossTimeout term covers a node that has not yet noticed it is alone. The final Dwell absorbs advert timing.

With the defaults, four history plans and at most 10 provisioned rendezvous plus allowed entries per band, the longest list is 16 entries. That gives E = 48 s and B = 215 s. `Node.RecoveryBound()` computes B from a node's actual configuration. A shorter allowed list shortens B in proportion. In simulation, with coverage restored at 21 points across the search schedule, the worst recovery was 55 s.

No communication is possible while a node is outside all usable RF coverage, so B is measured from coverage returning, not from the node leaving.

**Measurement on hardware ([GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31)):**

- **t0** is when RF coverage returns: an attenuator is removed or a shield is opened.
- **t1** is when the returning node holds the mesh's current plan version and passes traffic to a peer on at least one band.
- Report t1 − t0 against the node's printed RecoveryBound(), for each acceptance case in section 9.

## 8. Default parameters

These are the defaults used by `chanmig.DefaultTiming()`. The code rejects combinations that break the bound's assumptions: Dwell and PeerWindow must each be at least two AdvertIntervals, and PeerLossTimeout must be longer than VerifyBound + FallbackBound.

| Parameter | Default | Why |
|---|---|---|
| AdvertInterval | 1 s | One ~150-byte frame per band per second is about 0.5 % of a 1 MHz HaLow channel at MCS0 per node |
| PeerWindow | 5 s | Five adverts; tolerates loss |
| Lead (proposal) | 30 s | Room for flooding, acks and clock skew |
| AbortMargin | 5 s | Time for a revert to flood before T |
| Stagger | 5 s | One band is verified before the next one moves |
| VerifyBound | 8 s | Eight advert chances on the new channel |
| FallbackBound | 8 s | Same on the previous channel |
| PeerLossTimeout | 20 s | Longer than verify + fallback, so a failed switch is not mistaken for loss |
| ColdBootGrace | 10 s | Rejoins at once when nothing changed |
| Dwell | 3 s | Three adverts per candidate, plus retune time |
| MaxLead | 10 min | Bounds how long a captured plan stays useful |
| RadioRetry | 10 s | Retries a failed radio without busy-looping |
| History | 4 plans | Covers several missed switches without growing E much |
| Memory bounds | 256 peers, 256 acks, 64 search entries per band | Fixed footprint on the target hardware |

Whether these timers are right for real HaLow and MT7916 retune times is a bench question for [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) and [GHO-39](https://linear.app/ghostnet-labs/issue/GHO-39). Changing a default changes this table and `DefaultTiming()` in the same pair of PRs.

## 9. Acceptance coverage

Rows follow the acceptance list in [maer-capabilities.md §3](../requirements/maer-capabilities.md#3-channel-migration-and-returning-node-recovery). The tests are in openmanetd `internal/chanmig/scenario_test.go` and `node_test.go`. They run against a simulated per-band medium. They show the protocol logic, not RF behavior.

| Case | Simulation test | Still needs hardware |
|---|---|---|
| Staged switch with acks, alternate path held | `TestScenario_stagedSwitch` | Real switch latency per driver ([GHO-39](https://linear.app/ghostnet-labs/issue/GHO-39)) |
| New channel unusable → fallback | `TestScenario_fallbackWhenNewChannelSilent` | Jammer on the bench |
| Missed announcement | `TestScenario_missedSwitchRecoversWithinBound` | t1 − t0 on [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) |
| Multiple missed switches and cold boot | `TestScenario_multipleMissedSwitchesAfterColdBoot` | Same, with power removed |
| Rendezvous channels lost | `TestScenario_rendezvousLoss`, `TestScenario_searchingNodesMeetOnRendezvous` | Same |
| HaLow-only reachability | `TestScenario_haLowOnlyCoverage` | Wi-Fi shielded or out of range |
| Partition decisions and merge | `TestScenario_partitionAndMerge` | Two groups separated by attenuation |
| Coordinator loss | `TestScenario_coordinatorLoss` | Coordinator powered off mid-plan |
| Clock loss | `TestScenario_unsyncedClockSwitchesOnRelativeTime` | Node with GNSS and NTP removed |
| Missing acks → revert | `TestScenario_abortWhenAcksMissing` | One-way link on the bench |
| Radio failure | `TestScenario_radioFailureDuringSwitch` | Radio disabled through its power switch |
| Replayed or forged plan | `TestScenario_replayedAndForgedPlansRejected` | None (pure software) |
| Recovery within the bound | `TestScenario_recoveryBoundAcrossReturnTimes` | Measured t1 − t0 (section 7) |

## 10. Integration boundary

The package takes four interfaces. Connecting them is the remaining [GHO-52](https://linear.app/ghostnet-labs/issue/GHO-52) work:

| Interface | What production code must provide |
|---|---|
| Transport | Per-band broadcast of adverts and acks inside the alfred payload codec. It must not call back into the node synchronously. |
| RadioSetter | Retune one band through mgmt and UCI or netlink. An error marks the radio failed. |
| Store | Persist the opaque plan records on flash. They are written only when a plan is accepted. |
| Clock | Wall time, plus whether GNSS or NTP currently disciplines it |

Setup and mesh-join must also provision the plan-authority public key, the mesh ID, the rendezvous list and the allowed list. Coordinators also need the private key. Exposing plan state in the EUD and adding an instrumentation snapshot belong to the same follow-up. A snapshot also needs a row in openmanetd `docs/instrumentation-snapshot.md`.
