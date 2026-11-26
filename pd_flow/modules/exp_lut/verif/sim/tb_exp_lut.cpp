// Self-checking Verilator testbench for exp_lut (SPEC.md sections 3 and 4).
// Built per REGISTERED value (RTL: -GREGISTERED=N; gate level: the netlist of one value) with
// --x-initial unique, so state elements power up random (randReset(2), seeded).
//
// Two references are checked at every point:
//   ref_iv : the golden model's interval file "shift lo hi W" (golden_model.py intervals:
//            exact rationals, analytic thresholds, math + decimal exp)
//   ref_fp : this file's own formula in double precision: D' = floor(D / 2^shift + 0.5)
//            (exact in double for D < 2^22), W = floor(255 * exp(-D' / 4) + 0.5)
// Modes (exit 0 only if mismatches == 0 and the expected number of points/cycles ran):
//   sim exh0 <iv>               REGISTERED=0: every (D, shift), 2^26 points; clk, rst_n and
//                               start are varied pseudo-randomly at every point and must not
//                               change W; done == start at every point
//   sim exh1 <iv>               REGISTERED=1: every (D, shift) loaded with start (2^26 loads);
//                               after each load one hold cycle with different random D, shift
//                               (W must hold, done = 0); a reset (with start = 1) every 4,096
//                               loads; no change of W/done with inputs while clk is low or at
//                               the falling edge, on every cycle
//   sim seq <cycles> <seed> <iv>  REGISTERED=1: random rst_n/start/D/shift regimes from a random
//                               power-up state; the next-state rule is checked from the OBSERVED
//                               outputs on every cycle (also before the first reset), and a
//                               shadow reference after the first reset
//   sim vectors <file> <iv>     REGISTERED=1: golden-model vectors "rst_n start D shift done W"
//   sim powerup <seeds> <iv>    REGISTERED=1: the same stimulus from <seeds> random power-up
//                               states; the traces from the first reset on must be identical
#include "Vexp_lut.h"
#include "verilated.h"
#include <cinttypes>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static const uint32_t DMAX = (1u << 22) - 1;
static VerilatedContext* ctx;
static Vexp_lut* dut;
static uint64_t points = 0, cycles = 0, mismatches = 0, checked = 0;

static uint64_t rs = 1;
static inline uint64_t rnd() {  // xorshift64*
    rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27;
    return rs * 2685821657736338717ULL;
}
static inline bool chance(double p) { return (double)(rnd() >> 11) / 9007199254740992.0 < p; }

// ---------------------------------------------------------------- references
struct Iv { uint32_t lo, hi; int w; };
static std::vector<Iv> ivs[16];
static void load_iv(const char* f) {
    FILE* fp = fopen(f, "r");
    if (!fp) { printf("cannot open %s\n", f); exit(2); }
    unsigned s, lo, hi; int w; int n = 0;
    while (fscanf(fp, "%u %u %u %d", &s, &lo, &hi, &w) == 4) { ivs[s & 15].push_back({lo, hi, w}); ++n; }
    fclose(fp);
    for (int s = 0; s < 16; ++s)
        if (ivs[s].empty() || ivs[s].front().lo != 0 || ivs[s].back().hi != DMAX) { printf("bad interval file\n"); exit(2); }
    printf("intervals loaded: %d\n", n);
}
static int ref_iv(uint32_t d, unsigned s) {
    for (const Iv& v : ivs[s]) if (d >= v.lo && d <= v.hi) return v.w;
    return -1;
}
static int ref_fp(uint32_t d, unsigned s) {
    double dp = std::floor((double)d / (double)(1u << s) + 0.5);
    return (int)std::floor(255.0 * std::exp(-dp / 4.0) + 0.5);
}

static void report(const char* what, uint64_t n, int rst, int st, uint32_t d, unsigned s, int got_done, int got_w, int exp_done, int exp_w) {
    if (++mismatches <= 20)
        printf("MISMATCH(%s) n=%" PRIu64 " rst_n=%d start=%d D=%06x shift=%u done=%d W=%d exp_done=%d exp_W=%d\n",
               what, n, rst, st, d, s, got_done, got_w, exp_done, exp_w);
}

static void new_dut(uint64_t seed) {
    if (dut) { dut->final(); delete dut; }
    if (ctx) delete ctx;
    ctx = new VerilatedContext;
    ctx->randReset(2);
    ctx->randSeed((int)(seed & 0x7fffffff));
    dut = new Vexp_lut{ctx};
    dut->clk = 0; dut->rst_n = 1; dut->start = 0; dut->D = 0; dut->shift = 0;
    dut->eval();
}

// ---------------------------------------------------------------- REGISTERED = 0
static int run_exh0() {
    rs = 0xE0E0;
    for (unsigned s = 0; s < 16; ++s) {
        size_t vi = 0;
        for (uint32_t d = 0; d <= DMAX; ++d) {
            while (d > ivs[s][vi].hi) ++vi;
            int e1 = ivs[s][vi].w, e2 = ref_fp(d, s);
            uint64_t r = rnd();
            int clk = r & 1, rst = (r >> 1) & 1, st = (r >> 2) & 1;
            dut->clk = clk; dut->rst_n = rst; dut->start = st; dut->D = d; dut->shift = s;
            dut->eval();
            int w = dut->W, dn = dut->done;
            ++points;
            if (w != e1 || dn != st) report("exh0", points, rst, st, d, s, dn, w, st, e1);
            if (e1 != e2) report("refs-disagree", points, rst, st, d, s, dn, w, st, e2);
        }
    }
    printf("RESULT mode=exh0 points=%" PRIu64 " expected=%" PRIu64 " mismatches=%" PRIu64 "\n",
           points, (uint64_t)16 << 22, mismatches);
    return (mismatches == 0 && points == ((uint64_t)16 << 22)) ? 0 : 1;
}

// ---------------------------------------------------------------- REGISTERED = 1
// One clock cycle: inputs change with clk low (outputs must not move), rising edge, then the
// next-state rule from the observed outputs: done' = rst_n && start,
// W' = !rst_n ? 0 : start ? f(D, shift) : W. exp_w >= 0: also compare with that value.
static int cur_w() { return dut->W; }
static int cur_d() { return dut->done; }
static bool shadow_known = false;
static int shadow_w = 0;
static uint64_t shadow_checked = 0;
static void cycle(int rst, int st, uint32_t d, unsigned s, int exp_done = -1, int exp_w = -1) {
    d &= DMAX; s &= 15;
    int w0 = cur_w(), d0 = cur_d();
    dut->rst_n = rst; dut->start = st; dut->D = d; dut->shift = s; dut->clk = 0; dut->eval();
    if (cur_w() != w0 || cur_d() != d0) report("comb-path", cycles, rst, st, d, s, cur_d(), cur_w(), d0, w0);
    dut->clk = 1; dut->eval();
    int w1 = cur_w(), d1 = cur_d();
    int f = (rst && st) ? ref_iv(d, s) : 0;
    if (rst && st && f != ref_fp(d, s)) report("refs-disagree", cycles, rst, st, d, s, d1, w1, 1, ref_fp(d, s));
    int nw = !rst ? 0 : st ? f : w0, nd = (rst && st) ? 1 : 0;
    ++checked;
    if (w1 != nw || d1 != nd) report("step", cycles, rst, st, d, s, d1, w1, nd, nw);
    if (!rst) { shadow_known = true; shadow_w = 0; }
    else if (st && shadow_known) shadow_w = f;
    if (shadow_known) { ++shadow_checked; if (w1 != shadow_w) report("shadow", cycles, rst, st, d, s, d1, w1, nd, shadow_w); }
    if (exp_done >= 0 && d1 != exp_done) report("vector-done", cycles, rst, st, d, s, d1, w1, exp_done, exp_w);
    if (exp_w >= 0 && w1 != exp_w) report("vector-W", cycles, rst, st, d, s, d1, w1, exp_done, exp_w);
    dut->clk = 0; dut->eval();
    if (cur_w() != w1 || cur_d() != d1) report("negedge", cycles, rst, st, d, s, cur_d(), cur_w(), d1, w1);
    ++cycles;
}

static int run_exh1() {
    rs = 0xE1E1;
    uint64_t loads = 0;
    cycle(0, 1, rnd(), rnd());
    for (unsigned s = 0; s < 16; ++s) {
        size_t vi = 0;
        for (uint32_t d = 0; d <= DMAX; ++d) {
            while (d > ivs[s][vi].hi) ++vi;
            cycle(1, 1, d, s, 1, ivs[s][vi].w);
            ++loads;
            cycle(1, 0, (uint32_t)rnd(), (unsigned)rnd(), 0, ivs[s][vi].w);
            if ((loads & 4095) == 0) cycle(0, 1, (uint32_t)rnd(), (unsigned)rnd(), 0, 0);
        }
    }
    printf("RESULT_EXH1 loads=%" PRIu64 " (expected %" PRIu64 ") shadow_checked=%" PRIu64 "\n", loads, (uint64_t)16 << 22, shadow_checked);
    printf("RESULT mode=exh1 cycles=%" PRIu64 " checked=%" PRIu64 " mismatches=%" PRIu64 "\n", cycles, checked, mismatches);
    return (mismatches == 0 && loads == ((uint64_t)16 << 22)) ? 0 : 1;
}

static uint32_t rand_d() {
    double r = (double)(rnd() >> 11) / 9007199254740992.0;
    unsigned s = rnd() & 15;
    if (r < 0.4) {  // near an interval boundary
        const Iv& v = ivs[s][rnd() % ivs[s].size()];
        int64_t b = (rnd() & 1) ? v.lo : v.hi;
        b += (int64_t)(rnd() % 5) - 2;
        return (uint32_t)(b < 0 ? 0 : b > DMAX ? DMAX : b);
    }
    if (r < 0.6) return (uint32_t)(rnd() % 4096);
    if (r < 0.8) return (uint32_t)(rnd() % 2088961);
    return (uint32_t)(rnd() & DMAX);
}

static int run_seq(uint64_t n, uint64_t seed) {
    rs = seed;
    uint64_t regimes = 0;
    while (cycles < n) {
        double ps = (double[]){0.0, 0.1, 0.5, 0.9, 1.0}[rnd() % 5];
        double pr = (double[]){0.0, 0.0, 0.01, 0.2}[rnd() % 4];
        uint64_t len = 20 + rnd() % 2000;
        ++regimes;
        for (uint64_t i = 0; i < len && cycles < n; ++i)
            cycle(chance(pr) ? 0 : 1, chance(ps) ? 1 : 0, rand_d(), (unsigned)rnd());
    }
    printf("RESULT_SEQ regimes=%" PRIu64 " shadow_checked=%" PRIu64 "\n", regimes, shadow_checked);
    printf("RESULT mode=seq cycles=%" PRIu64 " expected=%" PRIu64 " checked=%" PRIu64 " mismatches=%" PRIu64 "\n", cycles, n, checked, mismatches);
    return (mismatches == 0 && cycles == n) ? 0 : 1;
}

static int run_vectors(const char* f) {
    FILE* fp = fopen(f, "r");
    if (!fp) { printf("cannot open %s\n", f); return 2; }
    char line[256];
    uint64_t nvec = 0, nval = 0;
    while (fgets(line, sizeof line, fp)) {
        int rst, st, dn; unsigned d, s; char wt[16];
        if (line[0] == '#' || sscanf(line, "%d %d %x %x %d %15s", &rst, &st, &d, &s, &dn, wt) != 6) continue;
        int ew = (wt[0] == 'x') ? -1 : (int)strtol(wt, nullptr, 16);
        cycle(rst, st, d, s, dn, ew);
        ++nvec; if (ew >= 0) ++nval;
    }
    fclose(fp);
    printf("RESULT mode=vectors cycles=%" PRIu64 " values_checked=%" PRIu64 " mismatches=%" PRIu64 "\n", nvec, nval, mismatches);
    return (mismatches == 0 && nvec > 0) ? 0 : 1;
}

static int run_powerup(int nseeds) {
    std::vector<std::vector<int>> traces;
    std::vector<int> init_w;
    int distinct = 0;
    for (int sd = 1; sd <= nseeds; ++sd) {
        new_dut(0x51ED0000ULL + sd * 7919ULL);
        shadow_known = false;
        init_w.push_back(cur_w() | (cur_d() << 8));
        rs = 0xC0FFEE;                        // identical stimulus for every seed
        for (int i = 0; i < 50; ++i) cycle(1, 0, rand_d(), (unsigned)rnd());   // no start, no reset
        cycle(0, (int)(rnd() & 1), rand_d(), (unsigned)rnd());
        std::vector<int> t;
        for (int i = 0; i < 3000; ++i) {
            cycle(chance(0.01) ? 0 : 1, chance(0.3) ? 1 : 0, rand_d(), (unsigned)rnd());
            t.push_back(cur_w() | (cur_d() << 8));
        }
        traces.push_back(t);
        if (traces.size() > 1 && t != traces[0]) { ++mismatches; printf("MISMATCH(powerup) seed %d trace after reset differs\n", sd); }
    }
    for (size_t i = 0; i < init_w.size(); ++i) {
        bool seen = false;
        for (size_t j = 0; j < i; ++j) seen |= init_w[j] == init_w[i];
        distinct += !seen;
    }
    printf("RESULT_POWERUP seeds=%d distinct_initial_state=%d\n", nseeds, distinct);
    printf("RESULT mode=powerup cycles=%" PRIu64 " checked=%" PRIu64 " mismatches=%" PRIu64 "\n", cycles, checked, mismatches);
    return (mismatches == 0 && distinct > 1) ? 0 : 1;
}

int main(int argc, char** argv) {
    if (argc < 3) { printf("usage: sim exh0|exh1 <iv> | seq <n> <seed> <iv> | vectors <f> <iv> | powerup <k> <iv>\n"); return 2; }
    const char* m = argv[1];
    load_iv(argv[argc - 1]);
    new_dut(0x5EED);
    if (!strcmp(m, "exh0")) return run_exh0();
    if (!strcmp(m, "exh1")) return run_exh1();
    if (!strcmp(m, "seq") && argc == 5) return run_seq(strtoull(argv[2], nullptr, 0), strtoull(argv[3], nullptr, 0));
    if (!strcmp(m, "vectors") && argc == 4) return run_vectors(argv[2]);
    if (!strcmp(m, "powerup") && argc == 4) return run_powerup(atoi(argv[2]));
    printf("bad arguments\n");
    return 2;
}
