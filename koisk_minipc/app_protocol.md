# 키오스크/앱 데이터 송신 규격 V2.0

### 데이터 전송 환경

- TCP/IP 통신
- **키오스크 → 허브 : 장기 연결(keep-alive)**
- **디바이스 → 허브 : 장기 연결(keep-alive)**
- 허브가 **두 연결을 “페어링”해서 프레임을 그대로 릴레이/라우팅**

### 사용 포트

- 미니PC : 8000 포트
- 앱 : 8001 포트

## 1) 전송(프레이밍) 규칙

### NDJSON

- **한 줄 = 한 JSON**
- 각 메시지 끝에 `\n` (LF) 추가
- 수신 측은 줄 단위로 JSON 파싱

예)

```
{"v":1,"type":"req","id":"1001", ...}\n
{"v":1,"type":"evt","id":"e-1", ...}\n
```

> 본 규격은 NDJSON 를 기본으로 설명합니다.
> 

---

## 2) 공통 메시지 프레임

모든 메시지는 아래 공통 구조를 사용합니다.

```
{
  "v": 1,
  "type": "req|resp|evt",
  "id": "string",
  "ts": 1730000000000,
  "from": "KIOSK-001|MINIPC-001",
  "cmd": "string",
  "data": {}
}
```

### 필드 정의

- `v` : 프로토콜 버전 (항상 `1`)
- `type`
    - `req` : 요청
    - `resp` : 응답 (요청에 대한 응답)
    - `evt` : 이벤트 (비동기 알림)
- `id`
    - `req`/`resp` 상관관계용 ID
    - `resp.id` 는 반드시 **요청의 id와 동일**
    - 생성 방식: UUIDv4 또는 증가값(문자열로 통일 권장)
- `ts` : 메시지 생성 시각 (epoch ms)
- `from` : 발신자 ID (키오스크/미니PC 식별)
- `cmd` : 명령 문자열 (권장 네이밍: `도메인.동사`)
- `data` : 명령별 데이터 payload

---

## 3) 응답(resp) 규격

응답은 반드시 `result` 를 포함합니다.

```
{
  "v": 1,
  "type": "resp",
  "id": "same-as-req-id",
  "ts": 1730000000000,
  "from": "MINIPC-001",
  "cmd": "bottle.start",
  "result": {
    "code": "OK|BUSY|INVALID_PARAM|INVALID_STATE|INTERNAL_ERROR|NOT_SUPPORTED",
    "detail": "string-or-number"
  },
  "data": {}
}
```

### result.code 정의

- `OK` : 정상 처리
- `BUSY` : 처리 불가(현재 작업 중 등)
- `INVALID_PARAM` : 파라미터 오류
- `INVALID_STATE` : 상태 오류(순서 위반 등)
- `INTERNAL_ERROR` : 내부 오류
- `NOT_SUPPORTED` : 미지원 명령

---

## 4) 공통 데이터 타입 / Enum

### 4.1 수취구(side)

- `"L"` : 좌
- `"R"` : 우

### 4.2 보틀 상태(bottle_state)

- `"IDLE"` : 대기(작업 없음)
- `"CREATING"` : 생성 중
- `"DONE"` : 생성 완료
- `"ERROR"` : 오류 상태
- `"CANCELED"` : 취소됨(향후 필요 시)

### 4.3 위치/마일스톤(stage)

- `"START"` : 생성 시작
- `"PRINTER_ARRIVED"` : 프린터 도착
- `"CHUTE_ARRIVED"` : 수취구 도착

---

## 5) 키오스크 → 미니PC 명령 (REQ)

### 5.1 보틀 생성 시작

- `cmd` : `bottle.start`
- 설명: 보틀 생성 프로세스 시작. **좌/우 수취구 선택 정보 포함**
- 요청(data)

```
{
  "job_id": "string",
  "side": "L|R",
  "flavor": "f1|f2|f3|f4"   // 선택(optional). 미지원 시 무시 가능
}
```

- 응답(data) 예시(선택)

```
{
  "job_id": "string",
  "accepted": true
}
```

### 예시

**REQ**

```
{"v":1,"type":"req","id":"1001","ts":1730000000000,"from":"KIOSK-001","cmd":"bottle.start","data":{"job_id":"J-20260118-0001","side":"L", "flavor":"f1"}}
```

**RESP**

```
{"v":1,"type":"resp","id":"1001","ts":1730000000100,"from":"MINIPC-001","cmd":"bottle.start","result":{"code":"OK","detail":"0"},"data":{"job_id":"J-20260118-0001","accepted":true}}
```

---

### 5.2 수취구 오픈

- `cmd` : `chute.open`
- 설명: 선택한 수취구(좌/우) 오픈
- 요청(data)

```
{
  "side": "L|R",
  "reason": "string (optional)"
}
```

### 예시

**REQ**

```
{"v":1,"type":"req","id":"1002","ts":1730000001000,"from":"KIOSK-001","cmd":"chute.open","data":{"side":"R","reason":"user_pickup"}}
```

**RESP**

```
{"v":1,"type":"resp","id":"1002","ts":1730000001100,"from":"MINIPC-001","cmd":"chute.open","result":{"code":"OK","detail":"0"},"data":{"side":"R","opened":true}}
```

---

### 5.3 긴급 중단 (Emergency Stop)

- `cmd` : `sys.emergency_stop`
- 설명: 진행 중인 동작을 **즉시 안전 정지**(모터/구동부 정지, 진행 작업 중단)시키는 명령
    - 장비 특성상 “즉시 정지”가 위험할 수 있으므로, 미니PC 내부에서는 **안전정지 시퀀스(감속/브레이크/락/밸브 차단 등)** 로 구현 권장
- 요청(data)

```
{
  "job_id": "string (optional)",
  "reason": "string (optional)",
  "force": true
}
```

- 응답(data) 예시(선택)

```
{
  "stopped": true,
  "job_id": "string (optional)"
}
```

### 예시

**REQ**

```
{"v":1,"type":"req","id":"1010","ts":1730000020000,"from":"KIOSK-001","cmd":"sys.emergency_stop","data":{"job_id":"J-20260118-0001","reason":"user_pressed_e-stop","force":true}}
```

**RESP**

```
{"v":1,"type":"resp","id":"1010","ts":1730000020100,"from":"MINIPC-001","cmd":"sys.emergency_stop","result":{"code":"OK","detail":"0"},"data":{"stopped":true,"job_id":"J-20260118-0001"}}
```

> 권장: 긴급 중단 처리 후, 미니PC는 상태 변화를 bottle.state(ERROR 또는 CANCELED 등)로도 evt 전송
> 

---

### 5.4 자가 점검 (Self Check)

- `cmd` : `sys.self_check`
- 설명: 장치 구성요소(프린터/모터/센서/도어/수취구 등)의 **자가 진단**을 수행하고 결과를 반환
- 요청(data)

```
{
  "scope": "ALL|PRINTER|SENSOR|MOTOR|CHUTE",
  "detail": true
}
```

- 응답(data)

```
{
  "overall": "PASS|FAIL",
  "items": [
    {
      "name": "printer",
      "status": "PASS|FAIL|WARN",
      "code": "string (optional)",
      "detail": "string (optional)"
    }
  ]
}
```

### 예시

**REQ**

```
{"v":1,"type":"req","id":"1011","ts":1730000030000,"from":"KIOSK-001","cmd":"sys.self_check","data":{"scope":"ALL","detail":true}}
```

**RESP**

```
{"v":1,"type":"resp","id":"1011","ts":1730000031500,"from":"MINIPC-001","cmd":"sys.self_check","result":{"code":"OK","detail":"0"},"data":{"overall":"PASS","items":[{"name":"printer","status":"PASS"}]}}
```

---

## 6) 미니PC → 키오스크 이벤트/알림 (EVT)

> 미니PC가 상태/위치 변화를 비동기 evt 로 전송합니다.
> 
> 
> 키오스크는 evt 수신 후 UI/흐름을 갱신합니다.
> 

### 6.1 보틀 위치 여부 (프린터 도착 알림)

- `cmd` : `bottle.printer_arrived`
- 트리거: 생성 시작 이후 **보틀이 프린터에 도착하는 시점**
- data

```
{
  "job_id": "string",
  "arrived": true
}
```

### 예시

```
{"v":1,"type":"evt","id":"e-2001","ts":1730000005000,"from":"MINIPC-001","cmd":"bottle.printer_arrived","data":{"job_id":"J-20260118-0001","arrived":true}}
```

---

### 6.2 보틀 상태 여부 (생성중/완료/오류 등)

- `cmd` : `bottle.state`
- 트리거: 상태 변경 시점마다
- data

```
{
  "job_id": "string",
  "state": "IDLE|CREATING|DONE|ERROR|CANCELED",
  "message": "string (optional)",
  "error": {
    "code": "string (optional)",
    "detail": "string (optional)"
  }
}
```

### 예시 (생성중)

```
{"v":1,"type":"evt","id":"e-2002","ts":1730000002000,"from":"MINIPC-001","cmd":"bottle.state","data":{"job_id":"J-20260118-0001","state":"CREATING"}}
```

### 예시 (완료)

```
{"v":1,"type":"evt","id":"e-2003","ts":1730000010000,"from":"MINIPC-001","cmd":"bottle.state","data":{"job_id":"J-20260118-0001","state":"DONE"}}
```

### 예시 (오류)

```
{"v":1,"type":"evt","id":"e-2004","ts":1730000009000,"from":"MINIPC-001","cmd":"bottle.state","data":{"job_id":"J-20260118-0001","state":"ERROR","message":"motor jam","error":{"code":"MOTOR_JAM","detail":"E42"}}}
```

---

### 6.3 보틀 위치별 여부 (시작/프린터 도착/수취구 도착)

- `cmd` : `bottle.stage`
- 트리거: 위치(마일스톤) 변경 시점마다
- 순서: `START` → `PRINTER_ARRIVED` → `CHUTE_ARRIVED` 로 진행되며, **최소 구현에서는 일부 stage만 발송해도 됨** (예: 수취구 도착만 전송)
- data

```
{
  "job_id": "string",
  "stage": "START|PRINTER_ARRIVED|CHUTE_ARRIVED",
  "side": "L|R (optional)",
  "extra": {}
}
```

### 예시 (시작)

```
{"v":1,"type":"evt","id":"e-2101","ts":1730000000001,"from":"MINIPC-001","cmd":"bottle.stage","data":{"job_id":"J-20260118-0001","stage":"START","side":"L"}}
```

### 예시 (프린터 도착)

```
{"v":1,"type":"evt","id":"e-2102","ts":1730000005000,"from":"MINIPC-001","cmd":"bottle.stage","data":{"job_id":"J-20260118-0001","stage":"PRINTER_ARRIVED"}}
```

### 예시 (수취구 도착)

```
{"v":1,"type":"evt","id":"e-2103","ts":1730000012000,"from":"MINIPC-001","cmd":"bottle.stage","data":{"job_id":"J-20260118-0001","stage":"CHUTE_ARRIVED","side":"L"}}
```

---

---

## 7) 명령 목록 요약

### 키오스크 → 미니PC (REQ)

- `bottle.start` : 보틀 생성 시작(좌/우 포함)
- `chute.open` : 수취구 오픈(좌/우 선택)
- `sys.emergency_stop` : 긴급 중단(안전 정지)
- `sys.self_check` : 자가 점검(진단 결과 반환)

### 미니PC → 키오스크 (EVT)

- `bottle.printer_arrived` : 프린터 도착 알림
- `bottle.state` : 생성 상태(생성중/완료/오류 등)
- `bottle.stage` : 위치 마일스톤(START/PRINTER_ARRIVED/CHUTE_ARRIVED)

## 2026/03/04 추가

- 보틀 생성시 flavor 추가

---

## 8) 규격과 구현 참고

- **flavor** (`bottle.start`): 규격에는 `f1|f2|f3|f4` 로 정의되어 있으며, 참조 구현(protocol.py / kiosk.py)에서는 아직 생략·미검증일 수 있음. 수신 측은 flavor 없이도 수락 가능하도록 하는것 고려 요청.
- **이벤트 순서**: 키오스크는 `bottle.printer_arrived` → `bottle.state`(들) → `bottle.stage` 등 evt 수신 순서에 의존할 수 있음. 미니PC는 규격에 정의된 순서로 전송하는 것을 요청.
- **sys.self_check**: `scope`가 `ALL`일 때 `items` 배열에 여러 항목(printer, sensor, motor, chute 등)을 넣을 수 있음. 단일 항목만 반환하는 구현도 허용.
- **앱(8001) vs 키오스크**: 동일 프로토콜(본 규격)을 사용하며, 허브는 포트로 키오스크/앱 구분 후 미니PC와 페어링하여 릴레이함.