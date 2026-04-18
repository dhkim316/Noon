# GPIO summary NODE-C

## IC2, UART
- GPIO 40: I2C SDA, PCF8575 DI 입력 확장기 데이터선. di_cfg.py (line 4)
- GPIO 41: I2C SCL, PCF8575 DI 입력 확장기 클럭선. di_cfg.py (line 3)
- GPIO 16: UART0 TX, RS485 송신. 캡 그리퍼 RGI100 통신에 쓰는 포트로 보입니다. rs485_port.py (line 8)
- GPIO 17: UART0 RX, RS485 수신. rs485_port.py (line 9)

## 액추에이터용 GPIO:
- GPIO 3: bottle_X STEP, 병 좌우 이송. C_cycle_test.py (line 174)
- GPIO 2: bottle_X DIR, 병 좌우 이송 방향. C_cycle_test.py (line 174)
- GPIO 5: bottle_Y STEP, 병 상하 이송. C_cycle_test.py (line 176)
- GPIO 4: bottle_Y DIR, 병 상하 이송 방향. C_cycle_test.py (line 176)
- GPIO 1: bottle_Z STEP, 병 전후 밀기. C_cycle_test.py (line 178)
- GPIO 0: bottle_Z DIR, 병 전후 방향. C_cycle_test.py (line 178)
- GPIO 7: cap_Y STEP, 캡 축 상하 이동. C_cycle_test.py (line 179)
- GPIO 6: cap_Y DIR, 캡 축 방향. C_cycle_test.py (line 179)
- GPIO 8: 병 그리퍼 DIR. C_cycle_test.py (line 182)
- GPIO 9: 병 그리퍼 EN. C_cycle_test.py (line 182)
- GPIO 14: 좌측 컨베이어 EN. C_cycle_test.py (line 166), dc_conveyorC.py (line 83)
- GPIO 15: 우측 컨베이어 EN. C_cycle_test.py (line 167)
