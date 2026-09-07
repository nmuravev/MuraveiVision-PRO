# Network replication (hub-and-spoke)

Topology: one **hub** (`mode=server`) and one or more **clients** (`mode=client`). Clients authenticate to the hub with a write-only `hub_pin` (operator PIN on the hub). There is no mesh/P2P in v3.2.

## What syncs

| Object | Direction | Transport | Notes |
|--------|-----------|-----------|--------|
| **Targets** (`network_targets`) | client ↔ hub | REST worker tick (~15 s) | class, confidence, GPS, notes, `source_video`, `crop_path` **string only** |
| **Chat messages** (`network_messages`) | client ↔ hub | same worker tick after targets | text body + sender; `synced_at` / `?since=` cursor |
| **Heartbeat / bases** | client → hub | REST | advertises **real LAN IPv4** (`MURAVEI_NETWORK_ADVERTISE_IP` override) |

## What does **not** sync (v3.2)

- Crop / screenshot **bytes** (`crop_path` is a path; remote file may be missing)
- Archive videos, recon **jobs**, sparse/mesh/splat packages
- WebSocket realtime chat (deferred to v3.3)
- Automatic LAN discovery beacons (deferred to v3.3)
- End-to-end encryption (LAN + JWT only)

## Operator UI

- **Сеть** (ViewId `network`) — mode, hub IP/port, bases, targets, «Отправить текущую цель», «Поделиться локацией»
- **Чат** (ViewId `chat`) — dedicated mosaic window; unread badge on mosaic title / Окна menu / panel header
- Location share = GPS-enriched target (+ `detection_id` in notes). If GPS missing → confirm: «GPS отсутствует — отправить без координат?»

## Engineer dual-instance smoke

See [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md#сеть-баз). Expect message round-trip within one worker tick (~15 s). Bases list should show non-loopback LAN IPs when NICs are present.

## Latency

Hub-and-spoke REST reconciler: typically **10–30 s**, not realtime. Offline compose leaves `synced_at=NULL` until the next successful push.
