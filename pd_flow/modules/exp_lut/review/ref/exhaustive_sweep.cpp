// Agent 2: exhaustive sweep of exp_lut against the exact-threshold reference (ref_thresholds.h).
// REGISTERED=0: all 2^22 x 16 (D, shift) points, combinational W and done == start (both values).
// REGISTERED=1: all 2^26 points with start every cycle (W/done checked the cycle after), plus
//   hold cycles (start=0 with random D/shift), reset cycles (W=0, done=0, reset beats start),
//   back-to-back starts and the one-cycle done pulse.
// Exit code 0 only if there are no mismatches. Prints a one-line JSON summary.
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include "Vexp_lut.h"
#include "verilated.h"
#include "ref_thresholds.h"

static unsigned ref_w(uint32_t D, unsigned s) {
    int k = 0;
    for (int j = 0; j < REF_NK; j++) if (D >= REF_TH[s][j]) k++;
    return REF_W[k];
}

static uint64_t rng = 0x9E3779B97F4A7C15ull;
static uint32_t rnd() { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return (uint32_t)rng; }

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vexp_lut* m = new Vexp_lut;
    uint64_t checks = 0, bad = 0;
    auto fail = [&](const char* what, uint32_t D, unsigned s, unsigned got, unsigned exp) {
        if (bad < 20) fprintf(stderr, "MISMATCH %s D=%u shift=%u got=%u exp=%u\n", what, D, s, got, exp);
        bad++;
    };
#if REGISTERED == 0
    for (unsigned s = 0; s < 16; s++)
        for (uint32_t D = 0; D < (1u << 22); D++) {
            unsigned st = (D ^ s) & 1;            // both start values, data-independent pattern
            m->D = D; m->shift = s; m->start = st; m->clk = D & 2; m->rst_n = (D >> 2) & 1;
            m->eval();
            checks++;
            unsigned e = ref_w(D, s);
            if (m->W != e) fail("W", D, s, m->W, e);
            if (m->done != st) fail("done", D, s, m->done, st);
        }
#else
    auto tick = [&]() { m->clk = 0; m->eval(); m->clk = 1; m->eval(); };
    // reset first (power-up state unspecified), reset beats start
    m->rst_n = 0; m->start = 1; m->D = 0; m->shift = 0; tick();
    if (m->W != 0 || m->done != 0) fail("reset", 0, 0, m->W, 0);
    unsigned expW = 0;
    for (unsigned s = 0; s < 16; s++)
        for (uint32_t D = 0; D < (1u << 22); D++) {
            m->rst_n = 1; m->start = 1; m->D = D; m->shift = s;
            m->clk = 0; m->eval();
            // before the edge: outputs still show the previous start's result
            if (m->W != expW) fail("W-before-edge", D, s, m->W, expW);
            m->clk = 1; m->eval();
            expW = ref_w(D, s); checks++;
            if (m->W != expW) fail("W", D, s, m->W, expW);
            if (m->done != 1) fail("done", D, s, m->done, 1);
            if ((D & 0xFFFF) == 0x1234) {          // sprinkle holds, a reset and a restart
                for (int h = 0; h < 3; h++) {
                    m->start = 0; m->D = rnd() & 0x3FFFFF; m->shift = rnd() & 15; tick(); checks++;
                    if (m->W != expW) fail("hold", m->D, m->shift, m->W, expW);
                    if (m->done != 0) fail("done-hold", m->D, m->shift, m->done, 0);
                }
                if ((D >> 16) % 7 == 3) {
                    m->rst_n = 0; m->start = rnd() & 1; tick(); checks++; expW = 0;
                    if (m->W != 0 || m->done != 0) fail("reset", D, s, m->W, 0);
                }
            }
        }
#endif
    printf("{\"registered\": %d, \"checks\": %llu, \"mismatches\": %llu}\n", REGISTERED,
           (unsigned long long)checks, (unsigned long long)bad);
    delete m;
    return bad ? 1 : 0;
}
