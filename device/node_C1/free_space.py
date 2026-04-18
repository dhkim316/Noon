import uos
import gc

fs = uos.statvfs('/')
block_size = fs[0]  # 블록 크기 (bytes)
total_blocks = fs[2]  # 전체 블록 수
free_blocks = fs[3]   # 남은 블록 수

total_size = block_size * total_blocks
free_size = block_size * free_blocks
used_size = total_size - free_size

print(f"=== 플래시 메모리 ===")
print(f"총 용량: {total_size // 1024} KB")
print(f"사용 중: {used_size // 1024} KB")
print(f"남은 용량: {free_size // 1024} KB")

gc.collect()

print(f"\n=== 램 메모리 ===")
print("Free memory:", gc.mem_free(), "bytes")
print("Allocated memory:", gc.mem_alloc(), "bytes")
print("Total memory:", gc.mem_free() + gc.mem_alloc(), "bytes")
