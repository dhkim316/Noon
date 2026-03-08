# 키오스크 ↔ 미니PC 한 사이클 정리

기준 문서: `protocol/app_protocol.md`  
전송 방식: TCP keep-alive + NDJSON(메시지 끝 `\n`)

## 1) 한 사이클(시작 → 종료) 요약

1. 키오스크가 `bottle.start` 요청을 전송한다.
2. 키오스크 `resp`로 접수 결과를 응답한다(`result.code=OK` 권장).
3. 미니PC가 진행 상태를 `evt`로 알린다.
4. 생성 완료 시 `bottle.state`를 `DONE`으로 전송한다.
5. 키오스크가 수취를 위해 `chute.open` 요청을 보낸다.
6. 미니PC가 수취구 오픈 응답을 보내면 한 사이클 종료.

## 2) 권장 이벤트 흐름

- 상태/위치 이벤트는 아래 순서가 가장 안전하다.
- `bottle.stage: START`
- `bottle.printer_arrived`
- `bottle.stage: PRINTER_ARRIVED`
- `bottle.state: CREATING`
- `bottle.stage: CHUTE_ARRIVED`
- `bottle.state: DONE`

## 3) 정상 사이클 예시(NDJSON)

```json
{"v":1,"type":"req","id":"1001","ts":1730000000000,"from":"KIOSK-001","cmd":"bottle.start","data":{"job_id":"J-20260307-0001","side":"L","flavor":"f1"}}
{"v":1,"type":"resp","id":"1001","ts":1730000000100,"from":"MINIPC-001","cmd":"bottle.start","result":{"code":"OK","detail":"0"},"data":{"job_id":"J-20260307-0001","accepted":true}}

{"v":1,"type":"evt","id":"e-2101","ts":1730000000200,"from":"MINIPC-001","cmd":"bottle.stage","data":{"job_id":"J-20260307-0001","stage":"START","side":"L"}}
{"v":1,"type":"evt","id":"e-2001","ts":1730000005000,"from":"MINIPC-001","cmd":"bottle.printer_arrived","data":{"job_id":"J-20260307-0001","arrived":true}}
{"v":1,"type":"evt","id":"e-2102","ts":1730000005100,"from":"MINIPC-001","cmd":"bottle.stage","data":{"job_id":"J-20260307-0001","stage":"PRINTER_ARRIVED"}}
{"v":1,"type":"evt","id":"e-2002","ts":1730000005200,"from":"MINIPC-001","cmd":"bottle.state","data":{"job_id":"J-20260307-0001","state":"CREATING"}}
{"v":1,"type":"evt","id":"e-2103","ts":1730000011000,"from":"MINIPC-001","cmd":"bottle.stage","data":{"job_id":"J-20260307-0001","stage":"CHUTE_ARRIVED","side":"L"}}
{"v":1,"type":"evt","id":"e-2003","ts":1730000011200,"from":"MINIPC-001","cmd":"bottle.state","data":{"job_id":"J-20260307-0001","state":"DONE"}}

{"v":1,"type":"req","id":"1002","ts":1730000011500,"from":"KIOSK-001","cmd":"chute.open","data":{"side":"L","reason":"user_pickup"}}
{"v":1,"type":"resp","id":"1002","ts":1730000011600,"from":"MINIPC-001","cmd":"chute.open","result":{"code":"OK","detail":"0"},"data":{"side":"L","opened":true}}
```

## 4) 종료 조건

- 아래 2개가 만족되면 해당 주문(Job) 사이클 종료로 본다.
- `bottle.state = DONE` 이벤트 수신
- `chute.open` 응답에서 `opened = true`

## 5) 예외 종료(참고)

- 진행 중 문제 발생 시 미니PC는 `bottle.state = ERROR`를 전송한다.
- 긴급 중단은 키오스크가 `sys.emergency_stop` 요청으로 트리거할 수 있다.
- 이 경우 정상 종료 대신 `ERROR` 또는 `CANCELED` 상태를 최종 상태로 처리한다.
