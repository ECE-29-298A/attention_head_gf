// Self-checking Verilator testbench for ripple_add #(N), N = NPARAM (1..64).
// Reference: s = (a + b + cin) mod 2^N in uint64 arithmetic (no bit-level chain).
//
// Usage: sim exhaustive            all 2^(2N+1) (a, b, cin), N <= 15; prints sum(s * mix(idx)) mod 2^64
//        sim random <count> <seed> xorshift64* random a, b, cin
//        sim vectors <file>        golden-model vectors "a b cin s" (hex); checks DUT
//                                  against the file's s and against the in-TB reference
// Exit status 0 only if mismatches == 0 and the expected vector count was applied.
#include "Vripple_add.h"
#include "verilated.h"
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifndef NPARAM
#error "NPARAM must be defined"
#endif
static const int N = NPARAM;
static const uint64_t MASK = (N >= 64) ? ~0ULL : ((1ULL << N) - 1);

static Vripple_add* dut;
static uint64_t mismatches = 0, applied = 0;

// splitmix64 finaliser: pseudo-random per-vector weight for the exhaustive checksum
static inline uint64_t mix(uint64_t z) {
    z += 0x9e3779b97f4a7c15ULL;
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

static inline uint64_t ref(uint64_t a, uint64_t b, uint64_t c) { return (a + b + c) & MASK; }

static inline uint64_t apply(uint64_t a, uint64_t b, uint64_t c) {
    dut->a = a;
    dut->b = b;
    dut->cin = c;
    dut->eval();
    ++applied;
    return (uint64_t)dut->s & MASK;
}

static void report(const char* what, uint64_t a, uint64_t b, uint64_t c, uint64_t got, uint64_t exp) {
    if (++mismatches <= 20)
        printf("MISMATCH(%s) N=%d a=0x%" PRIx64 " b=0x%" PRIx64 " cin=%" PRIu64 " s=0x%" PRIx64
               " exp=0x%" PRIx64 "\n", what, N, a, b, c, got, exp);
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    dut = new Vripple_add;
    if (argc < 2) { fprintf(stderr, "usage: sim exhaustive|random|vectors ...\n"); return 2; }
    const char* mode = argv[1];
    uint64_t expected = 0, checksum = 0;

    if (!strcmp(mode, "exhaustive")) {
        if (N > 15) { fprintf(stderr, "exhaustive needs N <= 15\n"); return 2; }
        expected = 1ULL << (2 * N + 1);
        for (uint64_t a = 0; a <= MASK; ++a)
            for (uint64_t b = 0; b <= MASK; ++b)
                for (uint64_t c = 0; c < 2; ++c) {
                    uint64_t s = apply(a, b, c), e = ref(a, b, c);
                    if (s != e) report("ref", a, b, c, s, e);
                    uint64_t idx = (a << (N + 1)) | (b << 1) | c;
                    checksum += s * mix(idx);
                }
    } else if (!strcmp(mode, "random") && argc >= 4) {
        expected = strtoull(argv[2], nullptr, 0);
        uint64_t x = strtoull(argv[3], nullptr, 0) | 1;
        auto next = [&x]() { x ^= x >> 12; x ^= x << 25; x ^= x >> 27; return x * 2685821657736338717ULL; };
        for (uint64_t i = 0; i < expected; ++i) {
            uint64_t a = next() & MASK, b = next() & MASK, c = next() >> 63;
            if (i & 1) b = (~a & MASK) ^ (next() & next() & next() & MASK);  // long carry chains
            uint64_t s = apply(a, b, c), e = ref(a, b, c);
            if (s != e) report("ref", a, b, c, s, e);
        }
    } else if (!strcmp(mode, "vectors") && argc >= 3) {
        FILE* f = fopen(argv[2], "r");
        if (!f) { perror(argv[2]); return 2; }
        char line[512];
        while (fgets(line, sizeof line, f)) {
            if (line[0] == '#' || line[0] == '\n') continue;
            uint64_t a, b, c, e;
            if (sscanf(line, "%" SCNx64 " %" SCNx64 " %" SCNx64 " %" SCNx64, &a, &b, &c, &e) != 4) {
                printf("BAD LINE: %s", line);
                ++mismatches;
                continue;
            }
            ++expected;
            uint64_t s = apply(a, b, c);
            if (s != e) report("golden", a, b, c, s, e);
            if (ref(a, b, c) != e) report("tb-ref-vs-golden", a, b, c, ref(a, b, c), e);
        }
        fclose(f);
        if (expected == 0) { printf("NO VECTORS\n"); ++mismatches; }
    } else {
        fprintf(stderr, "bad arguments\n");
        return 2;
    }
    dut->final();
    delete dut;
    printf("RESULT mode=%s N=%d vectors=%" PRIu64 " applied=%" PRIu64 " mismatches=%" PRIu64
           " checksum=0x%016" PRIx64 "\n", mode, N, expected, applied, mismatches, checksum);
    return (mismatches == 0 && applied == expected) ? 0 : 1;
}
