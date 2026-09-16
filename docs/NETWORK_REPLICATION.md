# Network replication (hub-and-spoke)

Topology: one **hub** (`mode=server`) and one or more **clients** (`mode=client`). Clients authenticate to the hub with a write-only `hub_pin` (operator PIN on the hub). There is no mesh/P2P in v3.2.

## What syncs

| Object | Direction | Transport | Notes |
|--------|-----------|-----------|--------|
| **Targets** (`network_targets`) | client ↔ hub | REST worker tick (~15 s) | class, confidence, GPS, notes, `source_video`, `crop_path` **string only** |
| **Chat messages** (`network_messages`) | client ↔ hub | REST worker tick (~15 s) **+ WS acceleration** | text body + sender + optional `attachment_id`; `synced_at` / `?since=` cursor; local browser `/ws/chat`; client backend **peer WS** to hub |
| **Recon packages** | client ↔ hub | chunked REST (≤1 GiB/artifact) | sparse/dense/mesh/splat; disk preflight; resume by chunk; unpack → `archive/recon/<job>/` |
| **Heartbeat / bases** | client → hub | REST | advertises **real LAN IPv4** (`MURAVEI_NETWORK_ADVERTISE_IP` override) |

## What does **not** sync (yet)

- Target `crop_path` **bytes** (path string only; chat attachments are separate)
- Archive videos, recon **jobs**, sparse/mesh/splat packages (N4)
- Automatic LAN discovery beacons (N5)
- End-to-end encryption (LAN + JWT only)

## Operator UI

- **Сеть** (ViewId `network`) — mode, hub IP/port, bases, targets, «Отправить текущую цель», «Поделиться локацией»
- **Чат** (ViewId `chat`) — dedicated mosaic window; unread badge on mosaic title / Окна menu / panel header
- Location share = GPS-enriched target (+ `detection_id` in notes). If GPS missing → confirm: «GPS отсутствует — отправить без координат?»

## Engineer dual-instance smoke

See [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md#сеть-баз). Expect message round-trip within one worker tick (~15 s). Bases list should show non-loopback LAN IPs when NICs are present.

## Latency

**Realtime path:** browser WS always to **local** backend; client-mode backend opens outbound peer WS to hub. **Fallback:** hub-and-spoke REST reconciler **10–30 s** when `ws_peer=down`. Offline compose leaves `synced_at=NULL` until the next successful push.
