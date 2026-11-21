# Equal realised load (descriptive)

Descriptive (test-day, not used for selection): detection of B at the smallest k on the grid whose
realised test-day false-alarm load is at most that of C at its frozen k, per day and seed. Same residuals,
topologies, persistence and scoring as scripts/36 (B needs no compute, so it acts at once).

| day | C at frozen k: detected | C false-alarm episodes | B at equal or lower load: detected | B false-alarm episodes |
| --- | --- | --- | --- | --- |
| recorded | 10/23 | 1 in 8.0 h | k = 3: 9/23 | 1 in 8.0 h |
| split | 10/21 | 0 in 2.7 h | k = 15: 8/21 | 0 in 2.7 h |
| split_s8 | 6/22 | 0 in 2.6 h | k = 15: 6/22 | 0 in 2.6 h |
| split_s9 | 10/21 | 0 in 2.6 h | k = 15: 7/21 | 0 in 2.6 h |
| split_s10 | 10/21 | 0 in 2.5 h | k = 15: 9/21 | 0 in 2.5 h |
| split_s11 | 8/22 | 0 in 2.4 h | k = 15: 6/22 | 0 in 2.4 h |
