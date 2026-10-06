# SmolLM2 through the one-tile RTL: actual generation tests

## Verdict

**All attention heads in SmolLM2-135M-Instruct now run in RTL during text generation.** All returned values, emitted attention weights, generated token IDs, and final logits match the independent integer software reference on the tested prompts.

**One complete pretrained decoder block also runs in RTL during generation**, with the other 29 blocks on the CPU. The sample continuations are coherent but changed, and this is not an accuracy benchmark.

**All 30 decoder blocks can execute the chosen integer arithmetic in RTL, but the tested full-block quantization damages the model badly.** The resulting text is garbled. This is an execution/correctness pass and a model-quality failure. It is not a working faithful full-model deployment yet. It does not prove that better quantization or additional precision passes cannot work.

## Fixed hardware under test

Unmodified `attention-extended/norm_odd.v`, `NB=7, DB=6, SERIAL=1`, the source/configuration used by the archived one-tile physical candidate. RTL SHA-256: `f3b00c90734ffc413ae35499773604e2392ffba8bb40ef1dc9698f3ddc9f3548`.

The effective shared accumulator width is 23 bits; dot-product maximum tracking is 22 bits. The safe full-range attention configuration previously established for this physical design is 128 tokens × 64 dimensions per scheduled head. Do not confuse this physically laid-out version with the earlier larger synthesis-only configurations.

No hardware redesign, place-and-route change, timing resimulation, fabricated silicon test, or new tapeout sign-off was performed in this study. These are clock-by-clock RTL simulations compiled by Verilator. Icarus independently cross-checked the new bridge and matched the same 63,302 cycles and returned outputs on a directed suite (including 576/1536-wide dot products, 576-wide RMS, a real attention head, and SiLU).

## Workload and coverage

| Path | Generated tokens / prompts | Checked returned arithmetic values | Checked attention weights | Simulated clock cycles |
|---|---:|---:|---:|---:|
| All 270 attention heads per token, all 30 layers | 24 / 3 | 518,400 | 45,630 | 103,235,324 |
| Complete first pretrained block; remaining blocks float | 24 / 3 | 391,680 | 1,521 | 1,183,981,432 |
| All 30 pretrained decoder blocks, plus final RMS norm | 4 / 1 | 1,571,328 | 2,700 | 4,729,280,732 |

Counts include prompt prefill. The first two paths process 30 total token positions (9 prompt tokens and 21 subsequent inputs). The all-block path processes 4 total token positions, starting with the one-token prompt “Hello”. All output values are asserted equal against independent NumPy integer equations; RTL results, not reference results, feed the next model operation. The reference arithmetic is evaluated on the host solely for verification, not substituted into the RTL data path. Separate software runs confirm **bit-exact equality of all 49,152 final logits at every generated step** for each RTL path.

“Checked arithmetic values” counts API-returned values; the SiLU routine internally invokes the attention circuit and its internal weight bytes are not included in that weight counter.

## What executes where

- **All-attention path:** the RTL calculates QK dot products, maximum tracking, exponent lookup, denominator sums, weighted V sums, and final division for all nine query heads in each of 30 layers. Q/K/V projections, RoPE, norms, MLPs, and residuals run in floating point on the CPU.
- **Complete-block paths:** the RTL additionally calculates both RMS norms and learned scales, Q/K/V and output projections, the multiply-adds for RoPE, both residual additions, gate/up/down projections, SiLU through two-entry attention, and elementwise SwiGLU products. The all-block path includes the final RMS norm too.
- **Host in every path:** weights/tensors/KV-cache storage; command scheduling; selecting causal key rows; quantization, exponent bookkeeping, and conversion of returned integer codes; RoPE coefficient generation and operand/sign packing; tokenization; embedding lookup; the final vocabulary/logit projection and greedy token selection. Thus **this is a hybrid LLM execution test, not an entirely self-contained LLM on the tile**. The host's final vocabulary matrix multiplication remains floating point.

Pretrained model dimensions read from the cached config: hidden width 576, intermediate width 1,536, 30 layers, 9 query heads, 3 KV heads, head dimension 64, vocabulary 49,152. Model weights were not trained or updated in this study. Model and tokenizer file hashes and Python package versions are saved in `provenance.json`.

## Sample continuations

| Prompt | Floating-point baseline | All-attention RTL | First full block RTL |
|---|---|---|---|
| Hello | , /  / I'm glad you're | , and I'm excited to see what |  the way to do this is by using |
| The capital of France is |  Paris. Paris is the largest city in |  Paris. Paris is the political, cultural |  located in the northern part of the country |
| Water freezes at |  night, and the ice is so thick |  night, and the ice is so thick |  night, and the sky is painted with |

All-block RTL, prompt “Hello”: **inying whoinis**. This matches the integer reference exactly and is a negative result for usable model quality.

The first predicted token agrees with the float baseline on 3/3 prompts for all-attention offload and 1/3 for first-block offload. Eight-token continuations match the baseline exactly on 1/3 prompts for attention offload. These are short greedy continuations from raw prompts, not a chat-template evaluation, held-out perplexity test, or general quality claim. Three offline calibration strings overlap the topics of the test prompts; quality should not be generalized from these samples.

## Quantization and range findings

Attention uses dynamic power-of-two INT8 quantization for Q/K/V and the existing 26-entry exponential LUT, with integer truncating normalization. Decoder projections use per-output-row INT8 weight quantization, dynamic input exponents, and fixed per-tensor output exponents calibrated offline with headroom. RMS uses integer square root, output scale 16, and quantized learned gamma; epsilon is not implemented. RoPE coefficients use a scale of 64. SiLU inputs have a fixed scale of 8 (positive representable limit 15.875). Residual and gate products are requantized to INT8 between operations. These choices preserve the existing interface but are a coarse inference conversion, not a tuned deployment recipe.

The all-block reference generates garbled text on all three tested prompts. RTL confirms that behavior on the four-token “Hello” continuation. This localizes the discrepancy to the chosen approximate/quantized computation relative to the float model, rather than a detected RTL-versus-reference bug. It does not isolate which quantization choice contributes most.

There is also a real general-input range limitation:

| Directed case | Correct unbounded result after output conversion | Actual fixed-width RTL output |
|---|---:|---:|
| 1,536 products of 127 × 127, output shift 17 | 127 (saturated) | -3 (accumulator wrapped) |
| RMS of 576 inputs all equal to 127, numerator factor 384 | 16 | 51 (square sum wrapped) |

Those directed tests deliberately exceed the accumulator range and are recorded as **expected range failures**, not passed mathematical operations. For the actual all-block RTL sample, the largest observed absolute completed linear dot product was 204,916, and the largest square sum was 2,301,595, both below the signed 23-bit positive limit of 4,194,303. Tests assert these bounds on each relevant operation. Modular intermediate additions can wrap and cancel; completed dot products within range remain exact. An arbitrary long INT8 vector is not guaranteed safe just because this particular pretrained trace fits. Deployment needs a range-safe quantization/tiling scheme.

## Cycle-derived execution cost

At the earlier physical candidate's assumed 10 MHz interface clock, **excluding host overhead**:

- All-block sample: 472.93 seconds for four processed token positions, or approximately **118.23 seconds per generated token** at this very short context.
- First-block sample: 118.40 seconds across 30 processed token positions, approximately **3.95 seconds per processed position**.
- All-attention sample: 10.32 seconds across its 30 processed positions, with contexts ranging from 1 to 12 tokens. This average is not an estimate for 128-token context.

The all-block path issued 427,504,896 MAC operations. Operand/command traffic and CPU operations add latency. This study uses an ideal ready/valid host driver; it does not benchmark a physical USB/SPI/board connection. Wall-clock simulator times are recorded separately in each JSON result and should not be mistaken for chip throughput.

## Reproduction and next step

The accompanying archive contains the unmodified RTL, compiled-simulation bridge source, Python integer oracle, model integration, build script, simulation logs, logits, result JSON, model-file hashes, and simulator cross-checks. It excludes downloaded model weights and tool installations. Follow `smol-rtl-test/README.md`.

For the current demonstration, use all-attention RTL offload or one selected full decoder block and clearly state the host's role. Before claiming all-block SmolLM2 works well, improve and validate the numerical scheme (including outlier handling, activation ranges, residual precision, and accumulator range guarantees), then rerun end-to-end comparisons. The current full-block path is functionally executable but not numerically adequate.
