# I2C (PCF8575용)
I2C = {
    "id": 0,
    "scl": 41,
    "sda": 40,
    "freq": 400_000,
}

DI = {
    "addr": 0x20,          # 점퍼 상태에 따라 달라질 수 있음(기본 0x20이 흔함)
    "invert_mask": 0xFFFF, # 예: 스위치가 GND로 떨어지는(active-low) 구조면 0xFFFF 권장
}

SENSORS = [
    # bit: 0~15 (PCF8575 P0~P15)
    {"id": 1,  "bit": 15, "name": "S1"},
    {"id": 2,  "bit": 0,  "name": "S2"},
    {"id": 3,  "bit": 14, "name": "S3"},
    {"id": 4,  "bit": 1,  "name": "S4"},
    {"id": 5,  "bit": 13, "name": "S5"},
    {"id": 6,  "bit": 2,  "name": "S6"},
    {"id": 7,  "bit": 12, "name": "S7"},
    {"id": 8,  "bit": 3,  "name": "S8"},
    {"id": 9,  "bit": 11, "name": "S9"},
    {"id": 10, "bit": 4,  "name": "S10"},
    {"id": 11, "bit": 10, "name": "S11"},
    {"id": 12, "bit": 5,  "name": "S12"},
    {"id": 13, "bit": 9,  "name": "S13"},
    {"id": 14, "bit": 6,  "name": "S14"},
    {"id": 15, "bit": 8,  "name": "S15"},
    {"id": 16, "bit": 7,  "name": "S16"},
]

# SENSORS = [
#     # bit: 0~15 (PCF8575 P0~P15)
#     {"id": 1,  "bit": 15, "name": "S1"},
#     {"id": 2,  "bit": 0,  "name": "S2"},
#     {"id": 3,  "bit": 14, "name": "S3"},
#     {"id": 4,  "bit": 1,  "name": "S4"},
#     {"id": 5,  "bit": 13, "name": "S5"},
#     {"id": 6,  "bit": 2,  "name": "S6_conv_bottle_front"},
#     {"id": 7,  "bit": 12, "name": "S7_conv_bottle_rear"},
#     {"id": 8,  "bit": 3,  "name": "S8_lift_hi"},
#     {"id": 9,  "bit": 11, "name": "S9_lift_mid"},
#     {"id": 10, "bit": 4,  "name": "S10_lift_lo"},
#     {"id": 11, "bit": 10, "name": "S11_front_bottle_grip"},
#     {"id": 12, "bit": 5,  "name": "S12_front_bottle_release"},
#     {"id": 13, "bit": 9,  "name": "S13_rear_bottle_grip"},
#     {"id": 14, "bit": 6,  "name": "S14_rear_bottle_release"},
#     {"id": 15, "bit": 8,  "name": "S15"},
#     {"id": 16, "bit": 7,  "name": "S16"},
# ]