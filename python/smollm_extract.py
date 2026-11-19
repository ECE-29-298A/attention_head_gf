"""Capture real SmolLM attention inputs and float outputs for chip comparison.

For every prompt (first 16 tokens: the chip's token limit), layer and head this
saves Q, K, V after RoPE and the model's own float attention output, before the
output projection. Position p attends to keys 0..p, so each prompt gives
N = 1..16 cases per head.

Run: .venv/bin/python python/smollm_extract.py   (needs torch + transformers)
Output arrays (P prompts, 30 layers, 9 query heads, 3 KV heads, T = 16, 64 dims):
  q, out: (P, 30, 9, T, 64)   k, v: (P, 30, 3, T, 64)   query head h uses KV head h // 3
"""
import argparse
from pathlib import Path

import numpy as np
import torch
import transformers.models.llama.modeling_llama as llama
from transformers import AutoModelForCausalLM, AutoTokenizer

T = 16
PROMPTS = [
    "The capital of France is Paris, which is known for the Eiffel Tower and its museums.",
    "Water freezes at zero degrees Celsius and boils at one hundred degrees at sea level.",
    "def fibonacci(n):\n    if n < 2:\n        return n\n    return fibonacci(n - 1) + fibonacci(n - 2)",
    "Once upon a time, a small robot lived in a quiet village at the edge of the forest.",
]


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM-135M")
    parser.add_argument("--out", type=Path, default=root / "build/smollm_attention.npz")
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32,
                                                 attn_implementation="eager").eval()

    captured = []
    original = llama.eager_attention_forward

    def capture(module, query, key, value, *a, **kw):
        out, weights = original(module, query, key, value, *a, **kw)
        captured.append([x[0].numpy().copy() for x in (query, key, value, out.transpose(1, 2))])
        return out, weights

    llama.eager_attention_forward = capture  # LlamaAttention looks this up on every call
    ids = []
    try:
        with torch.no_grad():
            for prompt in PROMPTS:
                tokens = tokenizer(prompt, return_tensors="pt").input_ids[:, :T]
                assert tokens.shape[1] == T, f"prompt shorter than {T} tokens: {prompt!r}"
                ids.append(tokens[0].numpy())
                model(tokens)
    finally:
        llama.eager_attention_forward = original

    layers = model.config.num_hidden_layers
    q, k, v, out = (np.stack([np.stack([c[i] for c in captured[p*layers:(p+1)*layers]])
                              for p in range(len(PROMPTS))]) for i in range(4))

    # Self-check: causal softmax(q·k/8)·v over the saved arrays reproduces the model output.
    group = q.shape[2] // k.shape[2]
    # einsum, not @: batched matmul here raises spurious FP warnings (numpy 2.0 + Accelerate)
    kh, vh = np.repeat(k, group, axis=2), np.repeat(v, group, axis=2)
    scores = np.einsum("...td,...sd->...ts", q, kh) / np.sqrt(q.shape[-1])
    scores = np.where(np.tril(np.ones((T, T), bool)), scores, -np.inf)
    w = np.exp(scores - scores.max(-1, keepdims=True))
    expected = np.einsum("...ts,...sd->...td", w / w.sum(-1, keepdims=True), vh)
    assert np.allclose(expected, out, atol=1e-4), "capture mismatch"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, q=q, k=k, v=v, out=out, token_ids=np.stack(ids),
                        prompts=np.array(PROMPTS), model=args.model)
    print(f"saved {args.out}: q {q.shape}, k {k.shape}, |q| max {abs(q).max():.1f}, "
          f"|k| max {abs(k).max():.1f}, |v| max {abs(v).max():.2f}")


if __name__ == "__main__":
    main()
