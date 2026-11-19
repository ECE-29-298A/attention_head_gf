---
name: kernel-roofline-explainer
description: Specialized skill for GPU kernel and ML accelerator performance analysis using the Roofline model. Guides agents through operational arithmetic intensity calculation, memory hierarchy saturation (HBM, L2, SRAM), compute-bound vs memory-bound classification, and optimization roadmaps (coalescing, tiling, tensor cores).
---

# Kernel Roofline Explainer Skill

This skill guides coding agents in analyzing GPU kernels (CUDA, Triton, OpenCL) and hardware accelerators using the **Roofline Performance Model**. It ensures agents make mathematically rigorous optimization decisions rather than guessing bottlenecks.

---

## 1. The Roofline Mathematical Formulation

The Roofline model bounds attainable performance ($P$, in $\text{TFLOP/s}$) as a function of **Operational Arithmetic Intensity** ($I$, in $\text{FLOPs/Byte}$):

$$P = \min\left(P_{\text{peak}}, I \times B_{\text{peak}}\right)$$

Where:
- $P_{\text{peak}}$: Peak hardware compute performance ($\text{TFLOP/s}$).
- $B_{\text{peak}}$: Peak memory bandwidth ($\text{GB/s}$ or $\text{TB/s}$).
- $I$: Arithmetic Intensity = $\frac{\text{Total Floating Point Operations}}{\text{Total DRAM Bytes Transferred}}$.

### The Knee Point (Ridge Point)
$$I_{\text{knee}} = \frac{P_{\text{peak}}}{B_{\text{peak}}}$$

- **If $I < I_{\text{knee}}$ (Memory Bound)**:
  - Performance is limited by memory bandwidth ($P = I \times B_{\text{peak}}$).
  - Adding more compute ALUs or Tensor Cores provides **zero speedup**.
  - **Goal**: Increase $I$ by maximizing data reuse (shared memory tiling, register caching) or maximize memory bus efficiency (coalesced 128-bit loads).
- **If $I \ge I_{\text{knee}}$ (Compute Bound)**:
  - Performance reaches the compute ceiling ($P_{\text{peak}}$).
  - **Goal**: Increase instruction throughput, hide pipeline latency, avoid instruction stalls, and leverage specialized matrix engines (Tensor Cores / WMMA).

---

## 2. Kernel Optimization Hierarchy (Order of Operations)

When optimizing a GPU kernel, agents MUST follow this sequence:

### Level 1: Global Memory Access Pattern (Coalescing)
- Ensure threads in a warp access consecutive memory addresses aligned to 32/64/128-byte transaction boundaries.
- Replace strided or pointer-chasing patterns with coalesced contiguous loads (`float4` / `int4`).

### Level 2: Shared Memory / SRAM Tiling (Data Reuse)
- Cache input matrix tiles in high-speed On-Chip SRAM / Shared Memory.
- Example: In Matrix Multiplication ($C = A \times B$):
  - Naive GEMM: $I \approx 0.25\ \text{FLOP/Byte}$ (severely memory-bound).
  - $16 \times 16$ Shared Memory Tiling: $I \approx 4.0\ \text{FLOP/Byte}$ ($16\times$ reuse).

### Level 3: Register File Tiling & Instruction-Level Parallelism (ILP)
- Keep hot sub-tiles in thread private registers (2D register tiling).
- Unroll loops to expose concurrent independent FMA instructions.

### Level 4: Tensor Core / Matrix Hardware Acceleration
- Use hardware matrix-multiply-accumulate instructions (NVIDIA WMMA, MMA PTX, or AMD Matrix Cores).
- Shifts peak compute ceiling from FP32 CUDA cores (e.g. 19.5 TFLOPS on A100) to Tensor Cores (e.g. 312 TFLOPS).

---

## 3. Reference Knee Points for Modern Accelerators

| Accelerator | FP32 Peak ($P_{\text{peak}}$) | Tensor Core FP16 | HBM Bandwidth ($B_{\text{peak}}$) | FP32 Knee Point ($I_{\text{knee}}$) |
| :--- | :--- | :--- | :--- | :--- |
| **NVIDIA A100 (40GB)** | 19.5 TFLOP/s | 312 TFLOP/s | 1,555 GB/s | **12.5 FLOP/Byte** |
| **NVIDIA H100 SXM** | 67 TFLOP/s | 989 TFLOP/s | 3,350 GB/s | **20.0 FLOP/Byte** |
| **NVIDIA RTX 4090** | 82.6 TFLOP/s | 330 TFLOP/s | 1,008 GB/s | **81.9 FLOP/Byte** |

---

## 4. Checklist for Kernel Analysis
- [ ] Has total FLOP count been calculated from matrix/tensor dimensions?
- [ ] Has minimum theoretical DRAM data transfer (bytes) been calculated?
- [ ] What is the calculated arithmetic intensity ($I = \text{FLOPs} / \text{Bytes}$)?
- [ ] Is the kernel memory-bound or compute-bound on the target hardware?
- [ ] Has shared memory tiling or register reuse been applied before resorting to low-level assembly?
