# Unified UI: origin, routing, sign-in and navigation

**Owner:** [GHO-69](https://linear.app/ghostnet-labs/issue/GHO-69) (decide the origin, sign-in and recovery route for the unified UI)  
**Status:** Accepted 2026-10-09 by Justin (decision card in the project thread). Recorded as D-037 in [../decisions.md](../decisions.md).  
**Implements:** D-036 (one primary OpenMANET UI with LuCI behind Advanced).

This file is the design for how the OpenMANET UI (openmanetd) and LuCI share one node web interface in release 1. It owns the routing table, the sign-in behavior, the recovery route and the navigation sketches. The decision itself lives in D-037. The current-state audit (parity matrix, configuration writers, cookies, first-boot guards) is [unified-ui-audit.md](unified-ui-audit.md) ([GHO-67](https://linear.app/ghostnet-labs/issue/GHO-67), docs PR #49). Implementation work: [GHO-70](https://linear.app/ghostnet-labs/issue/GHO-70) (proxy and config flag) and [GHO-71](https://linear.app/ghostnet-labs/issue/GHO-71) (Advanced entry), both in the openmanetd PR from branch `claude/project-thread-0s9sbx-gho70`.

## 1. Today

| Port | Server | Serves |
|---|---|---|
| 80 | uhttpd | LuCI (`/cgi-bin/luci/`), `/luci-static/`, `/ubus/`, the other `/cgi-bin/` helpers |
| 8080 | openmanetd frontend (HTTP) | OpenMANET UI (React SPA), `/api/*`, `/ws`, proxied `/rpc/*` and `/auth/*` |
| 8081 | openmanetd frontend (HTTPS, self-signed unless a cert is configured) | Same as 8080 |
| 8087 | openmanetd API | ConnectRPC API, used through the frontend's `/rpc/` proxy |

The two UIs are separate origins with separate sign-ins. Neither links to the other.

## 2. Options considered

### Option 1: OpenMANET proxies LuCI (accepted)

The openmanetd frontend server is the canonical origin (`https://<node>:8081`, plus `http://<node>:8080`). It reverse-proxies LuCI's absolute paths to uhttpd on loopback, so the browser sees LuCI at `https://<node>:8081/cgi-bin/luci/` on the same origin as the OpenMANET UI. uhttpd stays on :80 unchanged.

- For: one origin and one certificate prompt. LuCI keeps working as shipped, with no theme or path changes. uhttpd on :80 remains a recovery route that does not depend on openmanetd. Listen addresses do not change. It is behind a config flag that defaults to off.
- Against: users still type a port (:8081) until a later change moves the default entry point. The proxy is one more hop for LuCI traffic. LuCI cookies are issued as `sysauth_http` because uhttpd sees plain HTTP (section 4).

### Option 2: OpenMANET takes 80/443, uhttpd moves to loopback

openmanetd binds :80 and :443 and proxies LuCI from uhttpd, which listens only on 127.0.0.1.

- For: a clean URL (`https://<node>/`) and a single front door.
- Against: if openmanetd is down, there is no web recovery route; LuCI is reachable only over SSH port-forwarding. It needs a packages and firmware change to move uhttpd (uhttpd config, firewall, luci-ssl), it broadens openmanetd's bind addresses, and it is a large step to take before physical-node evidence (D-036). Rejected for release 1.

### Option 3: Link only

The OpenMANET UI links to `http://<node>/cgi-bin/luci/` on uhttpd. No proxy.

- For: no new server code.
- Against: two origins and two certificate stories, and an HTTPS page that links to plain HTTP. Users leave the OpenMANET origin, and nothing sets up the later move to a single front door. Rejected.

## 3. Routing (option 1)

The proxy is enabled by `frontend.luciProxy.enable` in `/etc/openmanetd/config.yml` (default `false`). Its upstream is `frontend.luciProxy.upstream` (default `http://127.0.0.1:80`). With the flag off, openmanetd behaves exactly as it does today.

| Request on `https://<node>:8081` (or `http://<node>:8080`) | Handled by | Path sent upstream |
|---|---|---|
| `/cgi-bin` and `/cgi-bin/...` (`luci`, `cgi-upload`, `cgi-download`, `cgi-backup`, `cgi-exec`, and the ubus fallback `/cgi-bin/luci/admin/ubus`) | proxy to uhttpd | unchanged, with the query string |
| `/luci-static/...` | proxy to uhttpd | unchanged |
| `/ubus` and `/ubus/...` | proxy to uhttpd | unchanged |
| `/rpc/...` | openmanetd API (:8087) | `/rpc` prefix stripped (existing behavior) |
| `/auth/...`, `/api/sysupgrade/...` | openmanetd API (:8087) | unchanged (existing behavior) |
| `/api/...`, `/ws` | openmanetd frontend handlers | not proxied |
| any other path | OpenMANET SPA (static file or `index.html`) | not proxied |

Rules:

- LuCI routes are matched before every other handler, so the SPA's `index.html` fallback never answers a LuCI path.
- Paths that are not in canonical form (`..`, `.` or `//` segments) are not proxied.
- Responses stream with no buffering, for backup downloads and `cgi-exec` output.
- The SPA's cross-origin isolation headers (COOP, COEP, Permissions-Policy) are not added to LuCI responses.
- If uhttpd is unreachable, the proxy returns 502 with a pointer to the direct route.
- The proxy never changes listen addresses.

uhttpd on :80 keeps serving everything it serves today.

## 4. Sign-in, sessions and CSRF

Release 1 keeps the two sign-ins separate. Sessions are not bridged or shared.

| | OpenMANET UI | LuCI through the proxy |
|---|---|---|
| Login | PAM, through `/auth/login` on the openmanetd API | LuCI's own login, rpcd `sysauth` |
| Cookie | `session`, `Path=/`, HttpOnly | `sysauth_http`, `path=/cgi-bin/luci/`, `SameSite=strict`, HttpOnly |
| Gate on the proxied paths | none (the OpenMANET session is not required to reach LuCI) | LuCI enforces its own login |
| CSRF | SPA calls carry the session cookie or a bearer token to the API | LuCI's per-session token is embedded in its pages and checked by LuCI, so it is unchanged |

Behavior the proxy guarantees:

- `Set-Cookie` from LuCI reaches the browser unchanged.
- `Location` is preserved. The one exception is an absolute `Location` that names the upstream itself (for example `http://127.0.0.1/cgi-bin/luci/`), which becomes path-only so the browser stays on the proxied origin. Redirects to any other host are untouched.
- The browser's `Host` header is forwarded, so any absolute URL LuCI builds names the proxied origin. `X-Forwarded-For`, `-Host` and `-Proto` are set by the proxy and inbound copies are discarded.
- The OpenMANET `session` cookie is not forwarded to LuCI. All other cookies are forwarded as sent.

HTTPS: uhttpd sees plain HTTP from loopback, so LuCI runs with `HTTPS` unset and issues `sysauth_http` without the `Secure` flag, even when the browser is on `https://<node>:8081`. The browser stores and returns it on the HTTPS origin, so sign-in works. uhttpd does not read `X-Forwarded-Proto`. Cookies are scoped by host and not by port, so the same `sysauth_http` cookie also works on `http://<node>/` directly.

Bench checks before the flag is turned on by default (open in GHO-70 and GHO-71):

1. LuCI login, logout and session expiry through `https://<node>:8081/cgi-bin/luci/` on a physical node.
2. uhttpd with `redirect_https` enabled (for example after installing `luci-ssl`): it may redirect proxied requests to its own HTTPS listener and the browser leaves the OpenMANET origin. The upstream must stay plain HTTP on loopback.
3. Firmware upload (`cgi-upload`) and backup download (`cgi-backup`, `cgi-download`) through the proxy.

## 5. Recovery route

- If openmanetd is down, crashed or misconfigured, LuCI is still at `http://<node>/cgi-bin/luci/` on uhttpd, port 80. This route does not depend on openmanetd.
- To turn the proxy off, set `frontend.luciProxy.enable: false` (or remove the key). The change is read on config reload.
- A later packages change could redirect uhttpd's `/` to the OpenMANET UI. That is out of scope here and needs its own decision; the recovery route must remain reachable.
- First boot moves to the OpenMANET setup wizard with the next openmanetd bump in firmware, gated on a CM5 bench run (D-038). Online firmware updates come from ghostnet-labs/firmware releases (D-039).

## 6. Configuration ownership

Each setting has exactly one persistent owner. No component keeps a duplicate persistent copy.

| Settings | Owner | Rule |
|---|---|---|
| Network, wireless, firewall, DHCP, system services | UCI (`/etc/config/*`) | OpenMANET UI pages that show or change these read and write UCI (through openmanetd) and keep no copy of their own. LuCI also writes UCI directly. |
| Daemon features (comms, BLOS, GNSS, auth, setup, instrumentation, `frontend.*` including `luciProxy`) | `/etc/openmanetd/config.yml` | Not mirrored into UCI. LuCI does not edit it. |

Where both UIs can write the same UCI option, the last write wins, and each UI rereads UCI when it opens a page rather than trusting a cached value. The audit lists today's competing writers.

## 7. Navigation sketches

The Advanced entry appears only when the proxy is enabled (openmanetd reports `luci_proxy_enabled: true` on `/api/system/info`). It is a normal link to `/cgi-bin/luci/` (a full-page handoff, no iframe), labeled "Advanced" with the description "Full router settings (LuCI)", built from Lattice shell primitives with a touch target of at least 44 px.

### Desktop (sidebar, wider than 768 px)

```
+-------------------------+--------------------------------------------------+
| ◇ OpenMANET             |  node-a3  [MESH OK] [GPS 3D] [BAT 87%]           |
|   Mesh Terminal      ◀  +--------------------------------------------------+
|                         |  DASHBOARD                                       |
| OPERATIONS              |  mesh / overview                                 |
| ▣ Dashboard   <-- home  |  +-----------+ +-----------+ +-----------+       |
| ) Comms                 |  | PEERS  4  | | LINK 41dB | | BAT 87%   |       |
| △ Topology              |  +-----------+ +-----------+ +-----------+       |
| ⊕ GPS / GNSS            |                                                  |
| ⌒ BLOS                  |                                                  |
|                         |                                                  |
| SYSTEM                  |                                                  |
| ≡ Settings              |  Settings -> Wireless = radio settings           |
|   (General, Wireless,   |  (channel, power, mesh ID) stay in the           |
|    Network, Firmware,   |  OpenMANET UI                                    |
|    Terminal, Logs)      |                                                  |
| ↗ Advanced              |  <-- full-page link to /cgi-bin/luci/            |
|   Full router settings  |      shown only when the proxy is on             |
|   (LuCI)                |                                                  |
|                         |                                                  |
| Operator   × Sign Out   |                                                  |
+-------------------------+--------------------------------------------------+
```

### Mobile (360 px wide, bottom tab bar)

```
+------------------------------------+
| node-a3   [MESH OK] [GPS 3D] [87%] |   <- device context (topbar chips)
+------------------------------------+
| DASHBOARD                          |
| mesh / overview                    |
| +--------------------------------+ |
| | PEERS                       4  | |
| +--------------------------------+ |
| | LINK                     41 dB | |
| +--------------------------------+ |
|                                    |
|  ...More sheet, when open:         |
| +--------------------------------+ |
| | ⌒ BLOS                         | |  48 px rows
| | ≡ Settings                     | |
| | ↗ ADVANCED                     | |  <- /cgi-bin/luci/
| |   Full router settings (LuCI)  | |
| | ⇥ Sign Out                     | |
| +--------------------------------+ |
+------------------------------------+
| Home | Comms | Topo | GPS | More   |
+------------------------------------+
```

### Flows

```
First boot (setup)
  https://<node>:8081/  ->  setup wizard (when setup.enabled and not complete)
                        ->  apply  ->  sign in  ->  Dashboard

Everyday operation
  Dashboard  ->  Comms / Topology / GPS / BLOS
  Settings -> Wireless   (radio settings: channel, power, mesh; owned by UCI)

Advanced handoff
  Sidebar or More sheet -> "Advanced"
    -> full page load of https://<node>:8081/cgi-bin/luci/   (same origin)
    -> LuCI login (sysauth) on first visit, then LuCI pages
       (network, firewall, DHCP, services, deeper wireless, recovery tools)

Return
  Browser Back, or open https://<node>:8081/ -> OpenMANET UI
  (the OpenMANET session is untouched by the LuCI visit, so no re-login
   unless it expired)
  LuCI theme header: "Back to OpenMANET" (GHO-73, packages #14)

Recovery
  openmanetd down  ->  http://<node>/cgi-bin/luci/ on uhttpd :80
```

Device context: the topbar chips (node ID, mesh, GPS, battery) are on every OpenMANET page. LuCI pages show LuCI's own header, which names the host, so the device stays identifiable after the handoff.

## 8. Out of scope for release 1

- Bridging or sharing sessions between OpenMANET and LuCI.
- Moving openmanetd to ports 80/443, or uhttpd to loopback (option 2).
- Redirecting uhttpd's `/` to the OpenMANET UI.
- Turning the proxy on by default; that waits for the bench checks in section 4 and Justin's sign-off (D-036).
