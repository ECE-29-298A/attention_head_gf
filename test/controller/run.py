"""Run isolated controller simulations; generated files stay in a temporary directory."""
import argparse
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python/src"))
from attention_model import chip_attention, dot4, exp_weight, pack_byte


def vectors():
    rng = random.Random(298)
    # Single token, negative scores, all-equal scores, extrema, and lost tails.
    cases = [
        ([1, 0, 0, 0], [[-8, 0, 0, 0]], [[-8, -1, 0, 7]]),
        ([-8] * 4, [[-8] * 4] * 16, [[-8] * 4] * 16),
        ([-8] * 4, [[7] * 4] * 16, [[7] * 4] * 16),
        ([0] * 4, [[0] * 4] * 2, [[0] * 4, [1] * 4]),
        ([1, 0, 0, 0], [[7, 0, 0, 0]] + [[-6, 0, 0, 0]] * 15,
         [[-8] * 4] + [[7] * 4] * 15),
        # The final key changes the maximum: no exponent may run prematurely.
        ([1, 0, 0, 0], [[x, 0, 0, 0] for x in range(-8, 8)],
         [[-8, 7, -1, 1] if x % 2 else [7, -8, 1, -1] for x in range(16)]),
        ([1, 0, 0, 0], [[-7, 0, 0, 0], [-5, 0, 0, 0], [-1, 0, 0, 0]],
         [[-8, 7, 0, 1], [7, -8, 1, 0], [-1, 1, -8, 7]]),
    ]
    for n in range(1, 17):
        for _ in range(8):
            vec = lambda: [rng.randint(-8, 7) for _ in range(4)]
            cases.append((vec(), [vec() for _ in range(n)], [vec() for _ in range(n)]))
    for q, k, v in cases:
        scores = [dot4(q, row) for row in k]
        weights = [exp_weight(max(scores), s) for s in scores]
        fields = [len(k), sum((x & 15) << (4 * i) for i, x in enumerate(q))]
        for rows in (k, v):
            for row in rows:
                fields.extend([pack_byte(*row[:2]), pack_byte(*row[2:])])
        fields.extend(x & 255 for x in chip_attention(q, k, v))
        fields.extend(s & 65535 for s in scores)
        fields.extend(weights)
        yield " ".join(str(x) for x in fields)


def build(verilator, work, controller, label):
    command = [verilator, "--binary", "--timing", "--assert", "-Wno-fatal",
               "--top-module", "tb_controller", "--Mdir", str(work / label),
               str(ROOT / "test/controller/tb_controller.sv"), str(controller)]
    command += [str(ROOT / "src" / name) for name in ("score_mac.v", "max_reg.v", "accum.v")]
    result = subprocess.run(command, cwd=work, text=True, capture_output=True, timeout=120)
    if result.returncode:
        print(result.stdout + result.stderr)
        raise SystemExit(result.returncode)
    for line in result.stderr.splitlines():
        if line.startswith("%Warning"):
            print(line, flush=True)
    return work / label / "Vtb_controller"


def simulate(binary, data, *args):
    result = subprocess.run([str(binary), f"+VECTORS={data}", *args],
                            cwd=binary.parent, text=True, capture_output=True, timeout=60)
    print(result.stdout, end="", flush=True)
    if result.returncode:
        print(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare-ref", help="Git revision containing the version-1 saved-score controller")
    args = parser.parse_args()
    verilator = shutil.which("verilator")
    if not verilator:
        raise SystemExit("Install Verilator to run this test.")
    with tempfile.TemporaryDirectory(prefix="attention-controller-") as temporary:
        work = Path(temporary)
        data = work / "vectors.txt"
        data.write_text("\n".join(vectors()) + "\n")
        current = build(verilator, work, ROOT / "src/attention_controller.sv", "current")
        # Different schedules supplement the deterministic Python input seed.
        for seed in (298, 2026, 16):
            simulate(current, data, f"+verilator+seed+{seed}")
        baseline = None
        if args.compare_ref:
            revision = subprocess.check_output(
                ["git", "rev-parse", "--verify", "--end-of-options", f"{args.compare_ref}^{{commit}}"],
                cwd=ROOT, text=True).strip()
            source = subprocess.check_output(["git", "show", f"{revision}:src/attention_controller.sv"], cwd=ROOT)
            old_controller = work / "baseline.sv"
            old_controller.write_bytes(source)
            baseline = build(verilator, work, old_controller, "baseline")
            print(f"Comparing version-1 controller at {revision}", flush=True)
        for latency in (2, 8, 32):
            timing = f"+MEM_CYCLES={latency}"
            current_log = simulate(current, data, timing)
            if baseline:
                old_log = simulate(baseline, data, timing, "+LEGACY")
                new_total = int(re.search(r"total_cycles=(\d+)", current_log)[1])
                old_total = int(re.search(r"total_cycles=(\d+)", old_log)[1])
                print(f"COMPARE memory_response_cycles={latency}: old={old_total}, new={new_total}, "
                      f"reduction={100*(old_total-new_total)/old_total:.2f}%", flush=True)


if __name__ == "__main__":
    main()
