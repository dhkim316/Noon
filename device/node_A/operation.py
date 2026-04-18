기기 동작 설명
1. 병 하나 프린터로 이송 하기 위해


설비구성
1. 병이 담긴 케이지 2세트가 있음(front케이지, rear케이지)
2. 케이지에 있는 병을 컨베이에 내려 놓음 (1회 12개, 병간 간격 = 90mm)
    2.1 front케이지에 있는 병을 내려놓는 동작은 
        def bottle_on_the_conveyor_auto(di, servo, grip_front, lift): 로 수행
    2.2 rear케이지에 있는 병을 내려놓는 동작은 
        def bottle_on_the_conveyor_auto_rear(di, servo, grip_rear, lift): 로 실행
3. 병이 올려진 상태에서 drop_one 동작으로 병 한개를 프린터 대기 위치로 떨어트린다




