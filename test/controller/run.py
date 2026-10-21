"""Run isolated controller simulations; generated files stay in a temporary directory."""
import os
from pathlib import Path
import random
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


def main():
    verilator = shutil.which("verilator")
    if not verilator:
        raise SystemExit("Install Verilator to run this test.")
    with tempfile.TemporaryDirectory(prefix="attention-controller-") as temporary:
        work = Path(temporary)
        data = work / "vectors.txt"
        data.write_text("\n".join(vectors()) + "\n")
        command = [verilator, "--binary", "--timing", "--assert", "-Wno-fatal",
                   "--top-module", "tb_controller", "--Mdir", str(work / "obj"),
                   str(ROOT / "test/controller/tb_controller.sv"),
                   str(ROOT / "src/attention_controller.sv")]
        command += [str(ROOT / "src" / name) for name in ("score_mac.v", "max_reg.v", "accum.v")]
        result = subprocess.run(command, cwd=work, text=True, capture_output=True)
        if result.returncode:
            print(result.stdout + result.stderr)
            raise SystemExit(result.returncode)
        warnings = [line for line in result.stderr.splitlines() if line.startswith("%Warning")]
        for warning in warnings:
            print(warning)
        subprocess.run([str(work / "obj/Vtb_controller"), f"+VECTORS={data}"],
                       cwd=work, check=True, env=os.environ.copy())


if __name__ == "__main__":
    main()
