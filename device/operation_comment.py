'''
NODE_A 병 공급/배출 구현 메모

1. 설비 구성
1) 병이 담긴 케이지는 2세트이다.
   - front cage
   - rear cage
2) 케이지의 병을 컨베이어에 내려놓는다.
   - 1회 적재량: 12개
   - 병 간 간격: 90mm
3) front 케이지 적재 함수
   - bottle_on_the_conveyor_auto(di, servo, grip_front, lift)
4) rear 케이지 적재 함수
   - bottle_on_the_conveyor_auto_rear(di, servo, grip_rear, lift)
5) 컨베이어에 병이 준비된 상태에서 bottle.drop_one 으로 병 1개를 프린터 대기 위치로 이동시킨다.


2. 요구 동작
1) front 에서 올린 병이 소진되면 rear 케이지 병을 컨베이어에 올린다.
2) rear 에서 올린 병이 소진되면 front 케이지 병을 컨베이어에 올린다.
3) 이 동작은 front/rear 케이지가 모두 소진될 때까지 반복한다.
4) front 공급 병 drop 시 time-out 이 나면 front 케이지 소진으로 판단한다.
5) rear 공급 병 drop 시 time-out 이 나면 rear 케이지 소진으로 판단한다.
6) front 와 rear 가 모두 소진되면 동작을 정지하고 bottle none 이벤트를 상위로 보고한다.


3. 현재 코드 기준 부족한 점
1) 현재 bottle.drop_one 은 1회 호출 후 끝나므로 front/rear 전환 시퀀스가 없다.
2) 현재 state 는 busy, s3_latched, s4_latched 정도만 있어 공급 source 상태를 기억하지 못한다.
3) 현재 구현은 drop 실패를 "병 없음" 과 "설비 이상" 으로 구분하기 어렵다.
4) 현재 수동 적재(S3/S4)와 자동 공급 상태 관리가 연결되어 있지 않다.
5) 현재 NODE_A 는 app_protocol.md 형식의 evt 를 직접 보내지 않고, device.md 형식만 송신한다.


4. 추가해야 할 상태값 제안
1) active_source
   - 현재 컨베이어 위 병 묶음의 출처
   - 값 예: "front", "rear", None
2) front_empty
   - front cage 소진 여부
3) rear_empty
   - rear cage 소진 여부
4) last_loaded_source
   - 마지막 적재 성공 source
5) bottle_none_reported
   - 양쪽 소진 이벤트 중복 송신 방지용 latch


5. 추가해야 할 동작 제안
1) bottle_drop_one()/conv.drop_one() 결과를 세분화해야 한다.
   - success
   - timeout
   - machine_error
   - sensor_error
2) 상위 시퀀스 함수가 필요하다.
   - 현재 source 로 drop 시도
   - time-out 이면 현재 source empty 처리
   - 반대 source 가 비어있지 않으면 적재 함수 실행
   - 적재 후 다시 drop 시도
   - 양쪽 모두 실패하면 bottle none 보고 후 정지
3) 적재 성공 시 해당 source 의 empty 상태를 False 로 복구하는 규칙이 필요하다.
4) 수동 적재(S3/S4) 발생 시에도 active_source 와 empty 상태를 같이 갱신해야 한다.


6. 구현 위치 제안
1) A_cycle_test.py 의 개별 기구 동작 함수는 가급적 그대로 유지한다.
   - bottle_on_the_conveyor_auto()
   - bottle_on_the_conveyor_auto_rear()
   - bottle_drop_one()
2) 상위 상태 관리와 분기 로직은 NODE_A_client.py 에 추가하는 방식이 안전하다.
3) 즉, 기존 기구 함수는 재사용하고 그 위에 자동 공급 상태기계를 얹는 구조가 적절하다.


7. 이벤트 보고 구조 제안
1) NODE_A 는 device.md 형식으로 MINIPC-001 에 evt 를 전송한다.
2) MINIPC 가 이를 수신하여 app_protocol.md 형식의 bottle.state evt 로 변환한다.
3) 따라서 NODE_A 쪽에는 아래 둘 중 하나의 장치 이벤트 규약이 필요하다.
   - op="error" + code="BOTTLE_NONE"
   - op="bottle.none"
4) app/kiosk 로 올라갈 최종 이벤트 예시는 아래와 같다.

{"v":1,"type":"evt","id":"e-2005","ts":1730000010500,"from":"MINIPC-001","cmd":"bottle.state","data":{"job_id":"J-20260118-0001","state":"ERROR","message":"no bottle available","error":{"code":"BOTTLE_NONE","detail":"front/rear exhausted"}}}

5) job_id 는 NODE_A 가 모르므로 MINIPC 가 현재 작업 job_id 와 매핑해서 채워야 한다.


8. 권장 구현 순서
1) NODE_A_client.py state 에 active_source, front_empty, rear_empty, bottle_none_reported 추가
2) bottle_drop_one 결과를 success/timeout/error 로 구분
3) front/rear 자동 전환 포함 상위 시퀀스 함수 추가
4) 양쪽 소진 시 device evt 전송
5) MINIPC 에서 app bottle.state ERROR/BOTTLE_NONE 로 변환
6) 수동 적재 시 empty 상태 해제 및 active_source 동기화 처리


9. 핵심 판단 기준
1) 병 없음 판정은 "현재 source 의 drop_one time-out" 기준으로 한다.
2) 양쪽 source 모두 time-out 이면 bottle none 으로 본다.
3) jam, motor error, sensor failure 는 bottle none 이 아니라 별도 설비 오류로 처리해야 한다.
'''



