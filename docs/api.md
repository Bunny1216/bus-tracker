# City Bus Tracker - API contract

Base URL: `http://127.0.0.1:8000` (local) or your HTTPS host. All bodies are JSON. Times are UTC, ISO 8601.
Changes to this file need agreement from Fahad and Raiyan.

## POST /api/ingest/
Called by the bus unit (or `tools/fake_bus.py`).

Headers: `Content-Type: application/json`, `X-API-Key: <key of the bus named in bus_id>`

| Field     | Type     | Required | Rule |
|-----------|----------|----------|------|
| `bus_id`  | string   | yes      | Must match a `Bus.code`, e.g. `BUS-01` |
| `lat`     | number   | yes      | -90 to 90 |
| `lng`     | number   | yes      | -180 to 180 |
| `speed`   | number   | no (0)   | km/h, 0 to 120 |
| `heading` | number   | no (0)   | degrees, 0 to 360 |
| `fix_time`| string   | no       | UTC time of the GPS fix, e.g. `2026-11-21T10:15:30Z`. Not more than 5 min in the future. Used to measure delay (`received_at - fix_time`). |

Extra rule: the position must lie within 5 km of the route's bounding box, otherwise `off_route`.

| Status | Meaning | Body |
|--------|---------|------|
| 201 | Stored | `{"ok": true, "id": 123}` |
| 400 | Invalid data, malformed JSON, or off route | `{"error": "invalid_data", "details": {...}}` or `{"error": "off_route", "detail": "..."}` |
| 401 | Missing/wrong key or unknown `bus_id` | `{"error": "unauthorized"}` |

```
curl -X POST http://127.0.0.1:8000/api/ingest/ -H "Content-Type: application/json" -H "X-API-Key: YOUR_KEY" \
  -d '{"bus_id":"BUS-01","lat":23.95,"lng":90.40,"speed":20,"heading":90,"fix_time":"2026-11-21T10:15:30Z"}'
```

## GET /api/buses/
Latest position of every bus that has reported at least once. Never cached.

```json
[{
  "code": "BUS-01", "route": 1, "lat": 23.9503, "lng": 90.3997, "speed": 36.0, "heading": 181.4,
  "updated": "2026-11-21T10:15:31.220Z", "seconds_ago": 2,
  "fix_time": "2026-11-21T10:15:30.900Z", "delay_seconds": 0.3
}]
```
`updated` is the server receive time; `seconds_ago` is computed by the server, so clients need no clock sync.
The web app greys a bus when `seconds_ago` (plus elapsed local time) exceeds 60.

## GET /api/routes/<id>/
```json
{ "id": 1, "name": "Gazipur Chowrasta - Abdullahpur",
  "path": [[24.0, 90.42], [23.999803, 90.419789]],
  "stops": [{"id": 1, "code": "S1", "name": "Gazipur Chowrasta", "lat": 24.0, "lng": 90.42, "order": 1}] }
```
`stops` are sorted by `order`. Unknown id returns 404 `{"detail": "Not found."}`.

## Firmware notes
- Send `fix_time` from the GPS UTC clock, not the ESP32 clock.
- Treat only `201` as success; retry on network errors and 5xx, drop the point on 400.