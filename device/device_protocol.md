# Device Protocol (NDJSON) - Simple Mode

## 1. Overview

This protocol defines the communication between **device nodes** and the **MiniPC controller** using **TCP + NDJSON**.

Transport:
- TCP/IP
- Long-lived connection (keep-alive)

Framing:
- NDJSON (Newline Delimited JSON)
- Each message is one JSON object terminated by '\n'

Example stream:

{"t":"hello","from":"NODE-1","to":"MINIPC-001","op":"hello","d":{"kind":"servo"}}
{"t":"evt","from":"NODE-1","to":"MINIPC-001","op":"sensor.state","d":{"S1":1}}

Encoding:
- UTF-8


## 2. Network Architecture

           NODE-1
             │
           NODE-2
             │
           NODE-3
             │
             ▼
        MiniPC TCP Server
          (single port)

- MiniPC opens one TCP server port
- Multiple nodes connect simultaneously
- Each connection is handled as an independent socket


## 3. Message Structure

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


## 4. Message Types

hello : node registration  
req   : command request  
resp  : command response  
evt   : event notification  
ping  : heartbeat request  
pong  : heartbeat response  


## 5. Node Registration

Node → MiniPC

{
 "t":"hello",
 "from":"NODE-1",
 "to":"MINIPC-001",
 "op":"hello",
 "d":{
   "kind":"servo",
   "fw":"1.0"
 }
}

MiniPC → Node

{
 "t":"resp",
 "from":"MINIPC-001",
 "to":"NODE-1",
 "op":"hello",
 "d":{"ok":true}
}


## 6. Command Request

MiniPC → Node

{
 "t":"req",
 "from":"MINIPC-001",
 "to":"NODE-SERVO",
 "op":"servo.move",
 "d":{
   "pos":120,
   "speed":300
 }
}


## 7. Command Response

Success

{
 "t":"resp",
 "from":"NODE-SERVO",
 "to":"MINIPC-001",
 "op":"servo.move",
 "d":{"ok":true}
}

Failure

{
 "t":"resp",
 "from":"NODE-SERVO",
 "to":"MINIPC-001",
 "op":"servo.move",
 "d":{"ok":false,"msg":"limit"}
}


## 8. Event Messages

Sensor state

{
 "t":"evt",
 "from":"NODE-IO",
 "to":"MINIPC-001",
 "op":"sensor.state",
 "d":{"S6":1,"S7":0}
}

Motion completed

{
 "t":"evt",
 "from":"NODE-SERVO",
 "to":"MINIPC-001",
 "op":"motion.done",
 "d":{"job":"cap_open","result":"ok"}
}


## 9. Node Status Event

{
 "t":"evt",
 "from":"NODE-SERVO",
 "to":"MINIPC-001",
 "op":"node.status",
 "d":{
   "state":"ready"
 }
}

Recommended states:

ready  
busy  
idle  
running  
error  
offline  


## 10. Heartbeat

MiniPC → Node

{
 "t":"ping",
 "from":"MINIPC-001",
 "to":"NODE-1",
 "op":"ping",
 "d":{}
}

Node → MiniPC

{
 "t":"pong",
 "from":"NODE-1",
 "to":"MINIPC-001",
 "op":"pong",
 "d":{}
}

Recommended interval: 5 ~ 30 seconds


## 11. Operation Naming Convention

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

Representative OP by class:

A_CLASS  
servo.home  
servo.move_mm  
lift.move_hi  
lift.move_mid  
lift.move_lo  
grip.front.hold  
grip.front.release  
grip.rear.hold  
grip.rear.release  
conveyor.drop_one  

C_CLASS  
cap.reset  
cap.grip_mm  
cap.release_mm  
cap.rotate_abs  
cap.rotate_rel  
cap.open  
cap.close  
bottle.grip.hold  
bottle.grip.release  
bottle.x.move  
bottle.y.move  
bottle.z.move  
cap.y.move  
conveyor.left.go  
conveyor.right.go  

C1_CLASS  
(See `C1_CLASS OP (required)` section below)  

A_CLASS OP (required):

servo.home  
`d`: {}  

servo.move_mm  
`d`: {"mm":280,"rpm":200,"direction":"forward|reverse"}  

lift.move_hi  
`d`: {}  

lift.move_mid  
`d`: {}  

lift.move_lo  
`d`: {}  

grip.front.hold  
`d`: {"sensor":"S11_front_bottle_grip"}  

grip.front.release  
`d`: {"sensor":"S12_front_bottle_release"}  

grip.rear.hold  
`d`: {"sensor":"S13_rear_bottle_grip"}  

grip.rear.release  
`d`: {"sensor":"S14_rear_bottle_release"}  

conveyor.drop_one  
`d`: {"wait_on_timeout_ms":35000,"drop_timeout_ms":5000,"tail_run_ms":2700}  

C_CLASS OP (required):

cap.reset  
`d`: {"full":true}  

cap.grip_mm  
`d`: {"mm":8,"force":65,"speed":50}  

cap.release_mm  
`d`: {"mm":30,"force":50,"speed":50}  

cap.rotate_abs  
`d`: {"target_deg":360,"speed":30,"force":50}  

cap.rotate_rel  
`d`: {"delta_deg":360,"speed":30,"force":50}  

cap.open  
`d`: {"turns":3,"pitch_mm":4.5,"rot_step_deg":360}  

cap.close  
`d`: {"turns":3,"pitch_mm":4.5,"rot_step_deg":360,"final_torque_boost":75}  

bottle.grip.hold  
`d`: {"sensor":"S11","timeout_ms":10000}  

bottle.grip.release  
`d`: {"timeout_ms":1000}  

bottle.x.move  
`d`: {"distance_mm":500,"speed_mm_s":500.0,"direction":"left|right","stop_sensor":"S7|S8|null"}  

bottle.y.move  
`d`: {"distance_mm":700,"speed_mm_s":500.0,"direction":"up|down","stop_sensor":"S3|S4|null"}  

bottle.z.move  
`d`: {"distance_mm":400,"speed_mm_s":500.0,"direction":"front|rear","stop_sensor":"S1|S2|null"}  

cap.y.move  
`d`: {"distance_mm":100,"speed_mm_s":500.0,"direction":"up|down","stop_sensor":"S5|S6|null"}  

conveyor.left.go  
`d`: {"sensor":"S9","timeout_ms":7000}  

conveyor.right.go  
`d`: {"sensor":"S10","timeout_ms":7000}  

C1_CLASS OP (required):

step.Left_End  
`d`: {}  

step.Right_End  
`d`: {}  

step.done  (evt)  
`d`: {"act":"step.Left_End","ok":true}  

error  (evt)  
`d`: {"act":"step.Left_End|step.Right_End","msg":"..."}  

C1_CLASS OP (optional/local actuator):

door.open  
`d`: {"run_ms":3000}  

door.close  
`d`: {"run_ms":3000}  


## 12. Error Event Example

{
 "t":"evt",
 "from":"NODE-IO",
 "to":"MINIPC-001",
 "op":"error",
 "d":{
   "code":"SENSOR_TIMEOUT",
   "msg":"S7 wait timeout"
 }
}


## 13. Implementation Notes

1. Messages must end with '\n'
2. Each line must contain one JSON object
3. Events (evt) do not require responses
4. Node identity must be declared via hello
