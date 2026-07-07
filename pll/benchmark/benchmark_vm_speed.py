import subprocess
import time
import os
import sys
from pathlib import Path

def main():
    # Paths
    here = Path(__file__).resolve().parent
    project_root = here.parent.parent # AOL_2/
    pll_dir = here.parent # pll/
    pll_file = project_root / "benchmark.pll"
    
    # Check if pll-cli exists
    cli_bin = pll_dir / "target" / "release" / "pll-cli.exe"
    if not cli_bin.exists():
        cli_bin = pll_dir / "target" / "release" / "pll-cli"
    
    if not cli_bin.exists():
        print(f"Error: PLL CLI binary not found at {cli_bin}. Please run 'cargo build --release' first.")
        sys.exit(1)
        
    print(f"=== PLL VM Speed Benchmark ===")
    print(f"CLI Binary: {cli_bin}")
    print(f"Script: {pll_file}\n")
    
    # Run the script multiple times to measure average speed
    runs = 10
    times = []
    
    # Estimation of instructions in benchmark.pll loop:
    # 100k iterations. Each iteration:
    # - Condition check (while i < 100000): load_var, push_num, lt, jif (4 insts)
    # - sum = sum + i: load_var, load_var, add, store_var (4 insts)
    # - i = i + 1: load_var, push_num, add, store_var (4 insts)
    # - Loop end: jmp (1 inst)
    # Total: ~13 bytecode instructions per iteration.
    # 100,000 iterations * 13 = ~1.3 million VM instructions.
    estimated_instructions = 1300000
    
    for r in range(1, runs + 1):
        start = time.perf_counter()
        result = subprocess.run(
            [str(cli_bin), "run", str(pll_file)],
            capture_output=True,
            text=True
        )
        end = time.perf_counter()
        
        if result.returncode != 0:
            print(f"Run {r} failed with error:\n{result.stderr}")
            sys.exit(1)
            
        elapsed = end - start
        times.append(elapsed)
        inst_rate = estimated_instructions / elapsed
        print(f"Run {r:2d}: {elapsed:.5f} seconds ({inst_rate/1e6:.2f} Million instructions/sec)")
        
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    avg_rate = estimated_instructions / avg_time
    
    print("\n=== Benchmark Results ===")
    print(f"Average Execution Time: {avg_time:.5f} seconds")
    print(f"Minimum Execution Time: {min_time:.5f} seconds")
    print(f"Maximum Execution Time: {max_time:.5f} seconds")
    print(f"Estimated VM Instruction Rate: {avg_rate/1e6:.2f} Million instructions/second")

if __name__ == "__main__":
    main()
