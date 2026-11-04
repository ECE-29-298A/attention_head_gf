# Accuracy report

Error = |chip output − float attention output|, in real output units (INT4 values span −8 to 7). The output is rounded to 1/16, so ~0.03 is the floor.

## INT4, random inputs

| Tokens | Trials | Chip mean | Chip p99 | Chip max | Old 23/32 max | Online max |
|---|---|---|---|---|---|---|
| 1 | 3000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 2 | 3000 | 0.0029 | 0.0326 | 0.0427 | 0.0920 | 0.0427 |
| 4 | 3000 | 0.0051 | 0.0351 | 0.0512 | 0.1104 | 0.0512 |
| 8 | 3000 | 0.0067 | 0.0378 | 0.0635 | 0.1044 | 0.0581 |
| 16 | 3000 | 0.0087 | 0.0396 | 0.0590 | 0.1193 | 0.0557 |

## INT4, nasty cases (16 tokens)

| Case | Chip max | Old 23/32 max | Online max |
|---|---|---|---|
| all scores negative | 0.0000 | 0.0000 | 0.0000 |
| all scores equal | 0.0000 | 0.0000 | 0.0000 |
| one dominant token | 0.3308 | 0.3308 | 0.3308 |
| close scores (D <= 3) | 0.0335 | 0.0681 | 0.0357 |
| rising scores | 0.0664 | 0.1308 | 0.0438 |

## INT8 (same design, wider registers), random inputs

Values span −128 to 127 here, so errors are also shown as a % of that range.

| Tokens | Trials | Mean | Max | Max as % of range | Avg # tokens with nonzero weight |
|---|---|---|---|---|---|
| 16 | 500 | 0.0002 | 0.1285 | 0.05% | 1.00 |
| 128 | 500 | 0.0006 | 0.2032 | 0.08% | 1.00 |

## Register widths seen

| Register | INT4 now (max seen, bits) | INT8 at 128 tokens (max seen, bits) |
|---|---|---|
| score S (signed) | 184, 9 | 46200, 17 |
| weight sum L | 877, 10 | 349, 9 |
| weighted sum O (signed) | 4185, 14 | 32640, 16 |

Max seen on random data, not the worst case. Worst case below.

## Register widths, worst case

| Config | S | L | O | Divider numerator (16 × O) |
|---|---|---|---|---|
| INT4, 16 tokens, 8-bit W (now) | 10 | 12 | 16 | 19 |
| INT4, 128 tokens, 8-bit W | 10 | 15 | 19 | 22 |
| INT4, 128 tokens, 12-bit W | 10 | 19 | 23 | 26 |
| INT8, 128 tokens, 8-bit W | 18 | 15 | 23 | 26 |
| INT8, 128 tokens, 12-bit W | 18 | 19 | 27 | 30 |

## Lost tail: one leader, everyone else far behind

Token 0 has the top score and value −8. All other tokens sit D below it with value 7. Each one alone barely matters, but a crowd adds up. 8-bit weights round each of them to 0 (D ≥ 13), so the chip just outputs −8.

| Tokens | D | Float | Chip (8-bit weights) | Error | 10-bit | 12-bit | 16-bit |
|---|---|---|---|---|---|---|---|
| 16 | 12 | -7.462 | -7.188 | 0.275 | 0.087 | 0.038 | 0.025 |
| 16 | 13 | -7.669 | -8.000 | 0.331 | 0.107 | 0.018 | 0.018 |
| 16 | 14 | -7.798 | -8.000 | 0.202 | 0.015 | 0.015 | 0.015 |
| 128 | 12 | -4.409 | -3.000 | 1.409 | 0.471 | 0.029 | 0.029 |
| 128 | 13 | -5.595 | -8.000 | 2.405 | 0.595 | 0.030 | 0.033 |
| 128 | 14 | -6.443 | -8.000 | 1.557 | 0.131 | 0.068 | 0.006 |

Wider columns use an exact e^(−D/2) table at that width (10-bit: 16 entries, 12-bit: 19, 16-bit: 24).

## Weight table: chip now (exact) vs old 23/32 trick

| D | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| chip now (exact) | 255 | 155 | 94 | 57 | 35 | 21 | 13 | 8 | 5 | 3 | 2 | 1 | 1 |
| old 23/32 trick | 255 | 158 | 94 | 59 | 35 | 22 | 13 | 8 | 5 | 3 | 2 | 1 | 1 |
| 255·e^(−D/2) | 255.0 | 154.7 | 93.8 | 56.9 | 34.5 | 20.9 | 12.7 | 7.7 | 4.7 | 2.8 | 1.7 | 1.0 | 0.6 |
