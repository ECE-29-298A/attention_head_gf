"""End-to-end: SmolLM with every attention head computed by the chip model.

Replaces softmax(q·k/8)·v in all 30 layers x 9 heads with the chip model
(smollm_compare.run); projections, RoPE, MLPs and norms stay float. On 16-token
windows (the chip's token limit) it compares each variant with the float model:
  perplexity of the real next token, top-1 agreement with float's prediction,
  and mean KL(float || chip) of the next-token distribution.
Then it greedy-generates a few prompts out to 16 tokens.

Eval text is this repo's own prose (docs/*.md), so it needs no download.

Run: .venv/bin/python python/smollm_e2e.py   (needs torch + transformers)
"""
import argparse
from pathlib import Path
import re

import torch
import transformers.models.llama.modeling_llama as llama
from transformers import AutoModelForCausalLM, AutoTokenizer

from smollm_compare import run

T = 16
FIXED = dict(per_channel=True, lut_res=4, out_frac=4)
VARIANTS = [
    ("float", None),
    ("original chip, host scores", dict(step2=False, per_channel=False, lut_res=2, out_frac=0)),
    ("chip today, host scores", dict(step2=False, **FIXED)),
    ("chip, truncating shift", dict(step2=True, **FIXED, score_round=False)),
    ("chip (RTL: 64-dim, rounded shift)", dict(step2=True, **FIXED, score_round=True)),
]
PROMPTS = ["The capital of France is", "Water freezes at", "Once upon a time, there was a"]

chip = None  # options for smollm_compare.run, or None for float attention
float_attention = llama.eager_attention_forward


def chip_attention(module, query, key, value, *args, **kwargs):
    """Drop-in for Llama's eager attention; LlamaAttention looks it up on every call."""
    if chip is None:
        return float_attention(module, query, key, value, *args, **kwargs)
    # (batch, heads, T, 64) -> run() wants two leading dims: (1, batch, heads, T, 64)
    q, k, v = (x.detach().double().numpy()[None] for x in (query, key, value))
    codes, scale = run(q, k, v, **chip)
    out = torch.from_numpy(codes * scale)[0].to(query.dtype)
    return out.transpose(1, 2).contiguous(), None


def eval_windows(tokenizer, count):
    """Non-overlapping 16-token windows of prose (lines that start with a letter) from docs/."""
    root = Path(__file__).resolve().parents[1]
    lines = [line for doc in sorted((root / "docs").glob("*.md"))
             for line in doc.read_text().splitlines() if re.match(r"[A-Za-z]", line)]
    ids = tokenizer(" ".join(lines), return_tensors="pt").input_ids[0]
    windows = ids[: len(ids) // T * T].view(-1, T)
    assert len(windows) >= count, f"only {len(windows)} windows of eval text"
    return windows[:count]


def greedy(model, tokenizer, prompt):
    ids = tokenizer(prompt).input_ids
    start = len(ids)
    while len(ids) < T:
        logits = model(torch.tensor([ids]), use_cache=False).logits
        ids.append(int(logits[0, -1].argmax()))
    return tokenizer.decode(ids[start:])


def main():
    global chip
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM-135M")
    parser.add_argument("--windows", type=int, default=400)  # docs/ holds ~426
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32,
                                                 attn_implementation="eager").eval()
    llama.eager_attention_forward = chip_attention
    windows = eval_windows(tokenizer, args.windows)
    targets = windows[:, 1:]

    rows, samples, ref = [], {}, None
    with torch.no_grad():
        for name, chip in VARIANTS:
            logp = torch.log_softmax(model(windows, use_cache=False).logits[:, :-1].double(), -1)
            if ref is None:
                ref = logp
            nll = -logp.gather(-1, targets[..., None]).mean()
            agree = (logp.argmax(-1) == ref.argmax(-1)).double().mean()
            kl = (ref.exp() * (ref - logp)).sum(-1).mean()
            rows.append(f"| {name} | {nll.exp():.2f} | {100 * agree:.1f}% | {kl:.4f} |")
            samples[name] = [greedy(model, tokenizer, p) for p in PROMPTS]

    print(f"{len(windows)} windows x {T - 1} predictions, all 30 layers x 9 heads on the chip model\n")
    print("| Attention | perplexity | top-1 agrees with float | KL from float |")
    print("|---|---|---|---|")
    print("\n".join(rows))
    for i, prompt in enumerate(PROMPTS):
        print(f"\n{prompt!r}")
        for name, _ in VARIANTS:
            print(f"  {name:34} {samples[name][i]!r}")


if __name__ == "__main__":
    main()
