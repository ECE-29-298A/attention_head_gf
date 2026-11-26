// Self-checking Verilator testbench for max_reg (22-bit signed running maximum, no reset).
// Built with --x-initial unique: the power-up value of M is random (randReset(2), seeded).
//
// Every clock cycle is checked three ways (SPEC.md section 4):
//   - registered output: M does not change when the inputs change with clk low, nor at
//     the falling edge;
//   - one-step relation from the observed state: M' == (en && (first || S > M)) ? S : M,
//     with S, M sign-extended to int32 (also before any first load, for the random M);
//   - sequence tracker: after a first load, M == running max of the accepted scores.
// Modes (exit 0 only if mismatches == 0 and the expected number of cycles ran):
//   sim vectors <file>                golden-model vectors "first en S M" (hex, M = x
//                                     unknown) also checked against the file's M
//   sim ctrl <cycles> <seed>          controller-style sequences (first = token==0 level,
//                                     en pulses, continue runs), plus a per-query check
//                                     against std::max over the stored list of scores
//   sim free <cycles> <seed>          unconstrained random first/en/S with regime switching
//   sim onestep <hib> <lob>           exhaustive one-step update over the reduced space
//                                     V x V x {en} x {first}, V = all values whose bits
//                                     [21:22-hib] and [lob-1:0] are free and whose middle
//                                     bits are all 0 or all 1 (2^(hib+lob+1) values)
//   sim powerup <seeds>               same stimulus from <seeds> random power-up values of M:
//                                     traces after the first load must be identical and correct
#include "Vmax_reg.h"
#include "verilated.h"
#include <algorithm>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static const uint32_t MASK = 0x3FFFFF;
static const int32_t MINV = -(1 << 21), MAXV = (1 << 21) - 1;
static const int32_t SCORE_MIN = -1040384, SCORE_MAX = 1048576;

static VerilatedContext* ctx;
static Vmax_reg* dut;
static uint64_t cycles = 0, mismatches = 0, seq_checked = 0, vec_checked = 0;
static bool ref_known = false;
static int32_t ref_max = 0;

static inline int32_t sx(uint32_t v) { return (int32_t)((v & MASK) << 10) >> 10; }
static inline uint32_t bits(int32_t v) { return (uint32_t)v & MASK; }
static inline uint32_t mnow() { return (uint32_t)dut->M & MASK; }

static uint64_t rs = 1;
static inline uint64_t rnd() {  // xorshift64*
    rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27;
    return rs * 2685821657736338717ULL;
}
static inline int32_t rrange(int32_t lo, int32_t hi) {
    return lo + (int32_t)(rnd() % (uint64_t)((int64_t)hi - lo + 1));
}
static inline bool chance(double p) { return (double)(rnd() >> 11) / 9007199254740992.0 < p; }
static inline int32_t clampv(int64_t v) { return (int32_t)std::min<int64_t>(MAXV, std::max<int64_t>(MINV, v)); }

static void report(const char* what, int f, int e, uint32_t s, uint32_t m0, uint32_t got, int64_t exp) {
    if (++mismatches <= 20)
        printf("MISMATCH(%s) cycle=%" PRIu64 " first=%d en=%d S=%06x M_before=%06x M=%06x exp=%s%06" PRIx64 "\n",
               what, cycles, f, e, s, m0, got, exp < 0 ? "?" : "", exp < 0 ? 0 : (uint64_t)exp);
}

// One clock cycle: inputs change with clk low, rising edge, falling edge. exp < 0: no file value.
static uint32_t cycle(int f, int e, uint32_t s, int64_t exp = -1) {
    s &= MASK;
    uint32_t m0 = mnow();
    dut->first = f; dut->en = e; dut->S_in = s; dut->clk = 0; dut->eval();
    if (mnow() != m0) report("comb-path", f, e, s, m0, mnow(), m0);
    dut->clk = 1; dut->eval();
    uint32_t m1 = mnow();
    uint32_t step = (e && (f || sx(s) > sx(m0))) ? s : m0;
    if (m1 != step) report("step", f, e, s, m0, m1, step);
    if (e && f) { ref_known = true; ref_max = sx(s); }
    else if (e && ref_known && sx(s) > ref_max) ref_max = sx(s);
    if (ref_known) { ++seq_checked; if (sx(m1) != ref_max) report("sequence", f, e, s, m0, m1, bits(ref_max)); }
    if (exp >= 0) { ++vec_checked; if (m1 != (uint32_t)exp) report("vector", f, e, s, m0, m1, exp); }
    dut->clk = 0; dut->eval();
    if (mnow() != m1) report("negedge", f, e, s, m0, mnow(), m1);
    ++cycles;
    return m1;
}

static void new_dut(uint64_t init_seed) {
    if (dut) { dut->final(); delete dut; delete ctx; }
    ctx = new VerilatedContext;
    ctx->randReset(2);
    ctx->randSeed((int)(init_seed & 0x7fffffff));
    dut = new Vmax_reg(ctx);
    dut->clk = 0; dut->first = 0; dut->en = 0; dut->S_in = 0;
    dut->eval();
    ref_known = false;
}

// ---------------------------------------------------------------- controller-style
static int32_t ctrl_score(const std::vector<int32_t>& sc) {
    double r = (double)(rnd() >> 11) / 9007199254740992.0;
    if (r < 0.1 && !sc.empty()) return sc[rnd() % sc.size()];                       // tie
    if (r < 0.2 && !sc.empty()) return clampv((int64_t)*std::max_element(sc.begin(), sc.end()) + (chance(0.5) ? 1 : -1));
    if (r < 0.3) return rrange(MINV, MAXV);
    return rrange(SCORE_MIN, SCORE_MAX);
}
static uint64_t queries = 0, query_checks = 0;
static void run_ctrl(uint64_t total) {
    bool started = false;
    int32_t qmax = 0;
    while (cycles < total) {
        int n = rrange(1, 16);
        bool cont = started && chance(0.25);
        for (int i = rrange(1, 6); i > 0; --i) cycle(1, 0, rnd());   // IDLE, token = 0
        if (!cont) {
            started = true;
            std::vector<int32_t> sc;
            for (int k = 0; k < n; ++k) {
                int gs = rrange(0, 9);
                int gap = gs < 2 ? gs : gs < 5 ? rrange(2, 12) : gs < 8 ? rrange(13, 40) : rrange(41, 1100);
                for (int g = 0; g < gap; ++g) cycle(k == 0, 0, rnd());
                int32_t s = ctrl_score(sc);
                sc.push_back(s);
                cycle(k == 0, 1, bits(s));
            }
            qmax = *std::max_element(sc.begin(), sc.end());   // list-based reference
            ++query_checks;
            if (sx(mnow()) != qmax) report("query-max", 0, 0, 0, 0, mnow(), bits(qmax));
        }
        for (int k = 0; k < n; ++k) {                           // pass 2 / continue run
            for (int g = rrange(0, 8); g > 0; --g) cycle(k == 0, 0, rnd());
            cycle(k == 0, 0, rnd());                            // score_done, en = 0
            for (int g = rrange(0, 4); g > 0; --g) cycle(0, 0, rnd());
        }
        ++query_checks;   // M must still hold the latest fresh query's maximum
        if (sx(mnow()) != qmax) report("hold-after-pass2", 0, 0, 0, 0, mnow(), bits(qmax));
        ++queries;
    }
}

// ---------------------------------------------------------------- unconstrained
static uint64_t regimes = 0;
static void run_free(uint64_t total) {
    static const double PF[] = {0.0, 1.0 / 64, 1.0 / 8, 0.5, 1.0};
    static const double PE[] = {0.05, 0.5, 0.95, 1.0};
    static const int32_t EXT[] = {MINV, MINV + 1, -1, 0, 1, MAXV - 1, MAXV};
    while (cycles < total) {
        double pf = PF[rnd() % 5], pe = PE[rnd() % 4];
        int mode = (int)(rnd() % 6);
        ++regimes;
        for (int len = rrange(50, 2000); len > 0 && cycles < total; --len) {
            int32_t m = sx(mnow()), s;
            switch (mode) {
            case 0: s = rrange(MINV, MAXV); break;
            case 1: s = EXT[rnd() % 7]; break;
            case 2: s = clampv((int64_t)m + rrange(-3, 3)); break;
            case 3: s = chance(0.5) ? m : sx(bits(m) ^ (1u << (rnd() % 22))); break;
            case 4: s = rrange(SCORE_MIN, SCORE_MAX); break;
            default: s = chance(0.5) ? sx((uint32_t)(rnd() & rnd())) : sx((uint32_t)(rnd() | rnd())); break;
            }
            cycle(chance(pf), chance(pe), bits(s));
        }
    }
}

// ---------------------------------------------------------------- reduced exhaustive
static uint64_t onestep_checks = 0;
static void run_onestep(int hib, int lob) {
    std::vector<uint32_t> v;
    int midw = 22 - hib - lob;
    uint32_t midones = ((1u << midw) - 1) << lob;
    for (uint32_t h = 0; h < (1u << hib); ++h)
        for (int mid = 0; mid < 2; ++mid)
            for (uint32_t l = 0; l < (1u << lob); ++l)
                v.push_back((h << (22 - hib)) | (mid ? midones : 0) | l);
    for (uint32_t m : v) {
        cycle(1, 1, m);
        for (uint32_t s : v)
            for (int e = 0; e < 2; ++e)
                for (int f = 0; f < 2; ++f) {
                    if (mnow() != m) cycle(1, 1, m);              // restore M = m
                    uint32_t exp = (e && (f || sx(s) > sx(m))) ? s : m;
                    uint32_t got = cycle(f, e, s);
                    ++onestep_checks;
                    if (got != exp) report("onestep", f, e, s, m, got, exp);
                }
    }
    printf("RESULT_SPACE values=%zu checks=%" PRIu64 " (expected %" PRIu64 ")\n", v.size(), onestep_checks,
           (uint64_t)v.size() * v.size() * 4);
    if (onestep_checks != (uint64_t)v.size() * v.size() * 4) ++mismatches;
}

// ---------------------------------------------------------------- power-up independence
static void run_powerup(int nseeds) {
    std::vector<uint32_t> init, first_trace;
    int pre_differs = 0;
    std::vector<uint32_t> pre0;
    for (int sd = 1; sd <= nseeds; ++sd) {
        new_dut(0x51ED0000ULL + sd * 7919ULL);
        init.push_back(mnow());
        rs = 0xC0FFEE;                                   // identical stimulus for every seed
        std::vector<uint32_t> pre, post;
        for (int i = 0; i < 200; ++i) pre.push_back(cycle(0, chance(0.5), rnd()));   // no first yet
        post.push_back(cycle(1, 1, bits(rrange(MINV, MAXV))));
        for (int i = 0; i < 3000; ++i) post.push_back(cycle(chance(1.0 / 32), chance(0.6), rnd()));
        if (sd == 1) { first_trace = post; pre0 = pre; }
        else {
            if (post != first_trace) { ++mismatches; printf("MISMATCH(powerup) seed %d trace after first load differs\n", sd); }
            if (pre != pre0) ++pre_differs;
        }
    }
    std::vector<uint32_t> u = init;
    std::sort(u.begin(), u.end());
    size_t distinct = std::unique(u.begin(), u.end()) - u.begin();
    printf("RESULT_POWERUP seeds=%d distinct_initial_M=%zu preamble_traces_differing=%d initial=", nseeds, distinct, pre_differs);
    for (size_t i = 0; i < init.size() && i < 8; ++i) printf("%06x ", init[i]);
    printf("\n");
    if (distinct < 2) { ++mismatches; printf("MISMATCH(powerup) power-up value of M not randomised\n"); }
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: sim vectors|ctrl|free|onestep|powerup ...\n"); return 2; }
    const char* mode = argv[1];
    uint64_t expected = 0;
    new_dut(argc > 3 ? strtoull(argv[3], nullptr, 0) : 12345);
    if (!strcmp(mode, "vectors") && argc == 3) {
        FILE* fp = fopen(argv[2], "r");
        if (!fp) { fprintf(stderr, "cannot open %s\n", argv[2]); return 2; }
        char line[256];
        while (fgets(line, sizeof line, fp)) {
            if (line[0] == '#') continue;
            unsigned f, e, s; char mtxt[32];
            if (sscanf(line, "%u %u %x %31s", &f, &e, &s, mtxt) != 4) continue;
            ++expected;
            int64_t exp = (mtxt[0] == 'x') ? -1 : (int64_t)strtoull(mtxt, nullptr, 16);
            cycle(f, e, s, exp);
        }
        fclose(fp);
    } else if (!strcmp(mode, "ctrl") && argc == 4) {
        expected = strtoull(argv[2], nullptr, 0); rs = strtoull(argv[3], nullptr, 0) | 1;
        run_ctrl(expected);
        printf("RESULT_CTRL queries=%" PRIu64 " query_checks=%" PRIu64 "\n", queries, query_checks);
        if (cycles >= expected) expected = cycles;   // a query in progress may run past the budget
    } else if (!strcmp(mode, "free") && argc == 4) {
        expected = strtoull(argv[2], nullptr, 0); rs = strtoull(argv[3], nullptr, 0) | 1;
        run_free(expected);
        printf("RESULT_FREE regimes=%" PRIu64 " (p_first, p_en, value distribution switched per regime)\n", regimes);
    } else if (!strcmp(mode, "onestep") && argc == 4) {
        int hib = atoi(argv[2]), lob = atoi(argv[3]);
        if (hib < 1 || lob < 1 || hib + lob > 20) { fprintf(stderr, "bad onestep space\n"); return 2; }
        new_dut(777);
        run_onestep(hib, lob);
        expected = cycles;
    } else if (!strcmp(mode, "powerup") && argc == 3) {
        run_powerup(atoi(argv[2]));
        expected = cycles;
    } else { fprintf(stderr, "bad arguments\n"); return 2; }
    printf("RESULT mode=%s cycles=%" PRIu64 " expected=%" PRIu64 " seq_checked=%" PRIu64 " vec_checked=%" PRIu64
           " mismatches=%" PRIu64 "\n", mode, cycles, expected, seq_checked, vec_checked, mismatches);
    dut->final();
    delete dut; delete ctx;
    return (mismatches == 0 && cycles == expected && cycles > 0) ? 0 : 1;
}
