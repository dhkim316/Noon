# Device

## 1. Folder Overview

This folder contains the device-side node implementations and the shared NDJSON/TCP protocol used to communicate with the MiniPC controller.

Current layout:

- `node_A`: NODE_A
- `node_C`: NODE_C
- `node_C1`: NODE_C1
- `device.md`: shared protocol and operation reference


## 2. Device Protocol (NDJSON)

### 2.1 Overview

This protocol defines the communication between **device nodes** and the **MiniPC controller** using **TCP + NDJSON**.

Transport:
- TCP/IP
- Long-lived connection (keep-alive)

Framing:
- NDJSON (Newline Delimited JSON)
- Each message is one JSON object terminated by '\n'

Example stream:

{"t":"hello","from":"NODE_A","to":"MINIPC-001","op":"hello","d":{"ok":true}}
{"t":"req","from":"MINIPC-001","to":"NODE_A","op":"bottle.drop_one","d":{}}

Encoding:
- UTF-8


### 2.2 Network Architecture

           NODE_A
             │
           NODE_C
             │
           NODE_C1
             │
             ▼
        MiniPC TCP Server
          (single port)

- MiniPC opens one TCP server port
- Multiple nodes connect simultaneously
- Each connection is handled as an independent socket


### 2.3 Message Structure

{
  "t": "...",
  "from": "...",
  "to": "...",
  "op": "...",
  "d": {...}
}

Field description:

t    : message type  
from : sender id  
to   : receiver id  
op   : operation name  
d    : payload data  


### 2.4 Message Types

hello : node registration  
req   : command request  
resp  : command response  
evt   : event notification  
ping  : heartbeat request  
pong  : heartbeat response  


### 2.5 Node Registration

Node → MiniPC

{
 "t":"hello",
 "from":"NODE_A",
 "to":"MINIPC-001",
 "op":"hello",
 "d":{"ok":true}
}

MiniPC → Node

{
 "t":"resp",
 "from":"MINIPC-001",
 "to":"NODE_A",
 "op":"hello",
 "d":{"ok":true}
}

### 2.6 Node Status Event

{
 "t":"evt",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"node.status",
  "d":{
   "state":"busy"
 }
}

Recommended states:

ready  
busy  
idle  
running  
error  
offline  


### 2.7 Heartbeat

MiniPC → Node

{
 "t":"ping",
 "from":"MINIPC-001",
 "to":"NODE_C1",
 "op":"ping",
 "d":{}
}

Node → MiniPC

{
 "t":"pong",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"pong",
 "d":{}
}

Recommended interval: 5 ~ 30 seconds


### 2.8 Operation Naming Convention

Rule:

- Base form: `device.action`
- Extended form: `device.subdevice.action`
- Parameterized action is allowed with suffix: `_mm`, `_abs`, `_rel`
- Use lowercase for device/action tokens
- Keep compatibility OP as-is when already deployed (example: `step.Left_End`)

Common OP:

hello  
ping  
pong  
sensor.state  
node.status  
error  

Representative OP by NODE:

NODE_A
bottle.drop_one  
bottle.on_the_conveyor
bottle.on_the_conveyor_man

NODE_C  
bottle.fill.f1.left
bottle.fill.f1.right
bottle.fill.f2.left
bottle.fill.f2.right
bottle.fill.f3.left
bottle.fill.f3.right
bottle.fill.f4.left
bottle.fill.f4.right

Optional payload for `NODE_C` `bottle.fill.*.*`:

- Base OP remains unchanged
- Timing override is passed in `d.fill_ms`
- If `fill_ms` is omitted, NODE_C uses its local default recipe
- MiniPC may override only the lower-level pump timing without changing the upper-level OP

Example:

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C",
 "op":"bottle.fill.f2.left",
 "d":{
   "fill_ms":{
     "f2":500,
     "f1":2000
   }
 }
}

NODE_C1
bottle.pick  
bottle.go_printer
door.open_left
door.open_right
door.close_left
door.close_right

### 2.9 NODE_A Bottle Supply Concept

`NODE_A` handles bottle supply in two stages:

- Supply stage: load bottles from the front or rear cage onto the conveyor buffer
- Drop stage: drop one bottle from the conveyor buffer

Bottle source structure:

- Bottles are stacked in two cages: `front` and `rear`
- The servo moves forward/backward to select which cage is active
- After the selected gripper releases, bottles are placed on the conveyor at fixed spacing
- Up to 12 bottles may exist on the conveyor buffer
- Depending on previous drops, some positions in the conveyor buffer may already be empty

Meaning of the main functions:

- `bottle_on_the_conveyor_manual`
  - manual preparation for the `front` cage
  - lowers one layer from the front cage and places bottles on the conveyor
- `bottle_on_the_conveyor_auto`
  - automatic preparation for the `front` cage
  - lowers one layer from the front cage and places bottles on the conveyor
- `bottle_on_the_conveyor_manual_rear`
  - manual preparation for the `rear` cage
  - lowers one layer from the rear cage and places bottles on the conveyor
- `bottle_on_the_conveyor_auto_rear`
  - automatic preparation for the `rear` cage
  - lowers one layer from the rear cage and places bottles on the conveyor
- `bottle.drop_one`
  - drops one bottle from the conveyor buffer
  - this is the actual single-bottle output step

Recommended operating interpretation:

1. First try `bottle.drop_one` using bottles already prepared on the conveyor
2. If the front-side supply is empty, run a front preparation function and retry
3. If the front side also times out, try the rear preparation path and retry
4. If both front and rear preparation/drop attempts time out, report `bottle none`

Timeout meaning:

- `bottle.drop_one` timeout after front supply attempt
  - front cage is empty or no more bottles are available from the front side
- `bottle.drop_one` timeout after rear supply attempt
  - rear cage is also empty
- front and rear both exhausted
  - overall bottle stock is empty
### 2.10 Error Event Example
{
 "t":"evt",
 "from":"NODE_C",
 "to":"MINIPC-001",
 "op":"error",
 "d":{
   "code":"SENSOR_TIMEOUT",
   "msg":"S7 wait timeout"
 }
}


### 2.11 Implementation Notes

1. Messages must end with '\n'
2. Each line must contain one JSON object
3. Events (evt) do not require responses
4. Node identity must be declared via hello


### 2.12 Protocol Examples

Command request examples

NODE_A: bottle.drop_one

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_A",
 "op":"bottle.drop_one",
 "d":{}
}

NODE_C: bottle.fill.f2.left

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C",
 "op":"bottle.fill.f2.left",
 "d":{}
}

NODE_C: bottle.fill.f2.left with timing override

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C",
 "op":"bottle.fill.f2.left",
 "d":{
   "fill_ms":{
     "f2":500,
     "f1":2000
   }
 }
}

NODE_C: bottle.go_left

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C",
 "op":"bottle.go_left",
 "d":{}
}

NODE_C: bottle.go_right

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C",
 "op":"bottle.go_right",
 "d":{}
}

NODE_C1: bottle.pick

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C1",
 "op":"bottle.pick",
 "d":{}
}

NODE_C1: bottle.go_printer

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C1",
 "op":"bottle.go_printer",
 "d":{}
}

NODE_C1: door.open_left

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C1",
 "op":"door.open_left",
 "d":{}
}

NODE_C1: door.open_right

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C1",
 "op":"door.open_right",
 "d":{}
}

NODE_C1: door.close_left

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C1",
 "op":"door.close_left",
 "d":{}
}

NODE_C1: door.close_right

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE_C1",
 "op":"door.close_right",
 "d":{}
}

Command response examples

NODE_A: bottle.drop_one success

{
 "t":"resp",
 "from":"NODE_A",
 "to":"MINIPC-001",
 "op":"bottle.drop_one",
 "d":{"ok":true}
}

NODE_A: bottle.drop_one failure

{
 "t":"resp",
 "from":"NODE_A",
 "to":"MINIPC-001",
 "op":"bottle.drop_one",
 "d":{"ok":false,"msg":"drop timeout"}
}

NODE_C: bottle.fill.f2.left success

{
 "t":"resp",
 "from":"NODE_C",
 "to":"MINIPC-001",
 "op":"bottle.fill.f2.left",
 "d":{"ok":true}
}

NODE_C: bottle.go_left success

{
 "t":"resp",
 "from":"NODE_C",
 "to":"MINIPC-001",
 "op":"bottle.go_left",
 "d":{"ok":true}
}

NODE_C: bottle.go_right failure

{
 "t":"resp",
 "from":"NODE_C",
 "to":"MINIPC-001",
 "op":"bottle.go_right",
 "d":{"ok":false,"msg":"move failed"}
}

NODE_C1: bottle.pick success

{
 "t":"resp",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"bottle.pick",
 "d":{"ok":true}
}

NODE_C1: bottle.go_printer success

{
 "t":"resp",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"bottle.go_printer",
 "d":{"ok":true}
}

NODE_C1: door.open_left success

{
 "t":"resp",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"door.open_left",
 "d":{"ok":true}
}

NODE_C1: door.open_right success

{
 "t":"resp",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"door.open_right",
 "d":{"ok":true}
}

NODE_C1: door.close_left success

{
 "t":"resp",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"door.close_left",
 "d":{"ok":true}
}

NODE_C1: door.close_right success

{
 "t":"resp",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"door.close_right",
 "d":{"ok":true}
}

Event examples

NODE_C: sensor.state

{
 "t":"evt",
 "from":"NODE_C",
 "to":"MINIPC-001",
 "op":"sensor.state",
 "d":{"S6":1,"S7":0}
}

NODE_A: node.status

{
 "t":"evt",
 "from":"NODE_A",
 "to":"MINIPC-001",
 "op":"node.status",
 "d":{"state":"ready"}
}

NODE_C1: node.status

{
 "t":"evt",
 "from":"NODE_C1",
 "to":"MINIPC-001",
 "op":"node.status",
 "d":{"state":"busy"}
}
