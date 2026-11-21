# Audit: library alone vs classic detector, per injection seed

Reproduction audit: per injection seed, library alone against the classic detector (a test that can go
either way, unlike combined = classic OR library), per grid and pooled, with the exact McNemar test.
01-Basic: library = rules active at the time (lib_prior), classic = D1. 02-Semiurban: library with
persistence L = 3, classic = SE-BDD. Instances share one benign base day per grid.

| seed | 01-Basic: library vs D1 detected (only library / only D1) | 02-Semiurban: library vs SE-BDD (only library / only SE-BDD) | pooled only library / only classic | McNemar p |
| --- | --- | --- | --- | --- |
| 7 | 7 vs 11 of 21 (0 / 4) | 10 vs 2 of 21 (8 / 0) | 8 / 4 | 0.3877 |
| 8 | 5 vs 9 of 21 (0 / 4) | 6 vs 3 of 22 (3 / 0) | 3 / 4 | 1.0000 |
| 9 | 9 vs 13 of 24 (0 / 4) | 10 vs 4 of 21 (6 / 0) | 6 / 4 | 0.7539 |
| 10 | 8 vs 14 of 23 (0 / 6) | 12 vs 7 of 21 (5 / 0) | 5 / 6 | 1.0000 |
| 11 | 8 vs 12 of 22 (0 / 4) | 8 vs 5 of 22 (3 / 0) | 3 / 4 | 1.0000 |
| all seeds (descriptive) | 0 / 22, p = 4.77e-07 | 25 / 0, p = 5.96e-08 | 25 / 22 | 0.7709 |
