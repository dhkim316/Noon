# AGENTS

## Scope

This workspace contains device-side code for `NODE_A`, `NODE_C`, and `NODE_C1`.

Use these rules as common guardrails for edits in this repository.


## Protocol

- Base protocol reference: [`device.md`](/Users/admin/Desktop/Noon/device/device.md)
- Protocol usage:
  - `kiosk_server.py` <-----> `NODE_test_server.py`: [`app_protocol.md`](/Users/admin/Desktop/Noon/device/app_protocol.md)
  - `NODE_test_server.py` <-----> `NODE_A_client.py`: [`device.md`](/Users/admin/Desktop/Noon/device/device.md)
  - `NODE_test_server.py` <-----> `NODE_C_client.py`: [`device.md`](/Users/admin/Desktop/Noon/device/device.md)
  - `NODE_test_server.py` <-----> `NODE_C1_client.py`: [`device.md`](/Users/admin/Desktop/Noon/device/device.md)
- Transport: TCP + NDJSON
- One message per line
- Common message shape:
  - `t`: message type
  - `from`: sender node id
  - `to`: receiver id
  - `op`: operation
  - `d`: payload

Canonical node ids:

- `NODE_A`
- `NODE_C`
- `NODE_C1`
- controller id: `MINIPC-001`


## Runtime Environments

- Code under `node_A`, `node_C`, and `node_C1` runs on RP2350 with MicroPython.
- [`NODE_test_server.py`](/Users/admin/Desktop/Noon/device/NODE_test_server.py) runs on Windows.


## Node Ops

Use the operation names defined in [`device.md`](/Users/admin/Desktop/Noon/device/device.md). Do not invent alternate spellings when an OP is already defined.

Current practical split:

- `NODE_A`
  - `bottle.on_the_conveyor`
  - `bottle.on_the_conveyor_man`
  - `bottle.drop_one`
  - `reboot`
- `NODE_C`
  - `bottle.fill.f1.left`
  - `bottle.fill.f1.right`
  - `bottle.fill.f2.left`
  - `bottle.fill.f2.right`
  - `bottle.fill.f3.left`
  - `bottle.fill.f3.right`
  - `bottle.fill.f4.left`
  - `bottle.fill.f4.right`
  - `reboot`
- `NODE_C1`
  - `bottle.pick`
  - `bottle.go_printer`
  - `door.open_left`
  - `door.open_right`
  - `door.close_left`
  - `door.close_right`
  - `reboot`


## Control Safety

- Do not change machine-control numeric values, ordering, time constants, or move sequence casually.
- When refactoring test code into functions, preserve the original execution order.
- Reuse existing actuator functions where possible instead of rewriting control logic.
- If a sequence already works on hardware, prefer wrapping or dispatching to it rather than rewriting it.


## Sensor State

- `sensor.state` must return sensor values in `d`.
- Use list form for deterministic ordering on MicroPython:
  - `d: [{"name":"S1","value":0}, ...]`
- Sort sensor output by the numeric part after `S` in `di_cfg.py` sensor names.
- Keep sensor names based on `di_cfg.py`, replacing `-` with `_` for output stability.


## Networking

- Node clients connect to the MiniPC/server on TCP port `5000`.
- `NODE_test_server.py` is the integrated host-side test server for up to 3 nodes.
- Some node clients also expose a file upload server on TCP port `7000`.
- File upload format:
  - first line: filename
  - remaining bytes: file body
  - overwrite existing file with the same name


## File Entry Points

- Each node folder should expose `main.py` that calls the node client `main()`.
- Keep node-specific client code in:
  - `node_A/NODE_A_client.py`
  - `node_C/NODE_C_client.py`
  - `node_C1/NODE_C1_client.py`


## Implementation Style

- Prefer small dispatch additions over broad rewrites.
- Keep protocol handling and machine-control logic separated when possible.
- For new host-side test helpers, prefer simple CLI input loops.
- When adding auto-trigger behavior from sensors, ensure repeated firing is blocked by state or latch logic.
