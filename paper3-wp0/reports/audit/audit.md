# Reproduction audit: event table and A/B/C ablation

Part 1, frozen scoring protocol and event table. For every process-attack instance of the recorded
test days (01-Basic, 02-Semiurban, 03-Rural) and of the main additional day (seed 7, 01-Basic and
02-Semiurban), the outcome of every detector and rule source is recomputed from the saved per-record
alarms, with the first alarm time and the activation time of the library rule. Strict credit is given
three ways: (a) as in the paper (rule learned or topology first met before the attack start),
(b) as (a) plus the measured certification compute time (the rule only acts once certification has
finished; 02-Semiurban and 03-Rural, where the replay itself applies the rule from the first record of
its topology), (c) first detection inside the recovery phase only, flagged.

Part 2, A/B/C on 02-Semiurban (recorded day and additional day). One state estimator, one residual
matrix (scripts/17), one candidate stream (one rule per topology, in order of first appearance), the
same persistence L and the same scoring:
  A  SE-BDD: one global threshold on max_i |r_i| (scripts/17), as published;
  B  per-channel, per-topology thresholds without the oracle: m_i = k x noise_i (noise_i as in
     scripts/18: train maximum, floored per measurement kind);
  C  B plus the physics check: m_i = max(k x noise_i, the proved margin part) taken from the stored
     rules of scripts/18 --prove (1.5 x the affine bound plus remainder).
Since C >= B channel by channel, C fires on a subset of B's records: C - B can only remove alarms.
Operating points: (i) the original k = 1.5; (ii) a matched false-alarm budget chosen on calibration
data only: noise recalibrated on the first half of the training records, k chosen as the smallest value
on a fixed grid whose false-alarm episodes per benign hour on the second half of the training records is
at most the target (fixed in advance: 0.5 episodes per hour), separately for B and C, frozen, then
applied to the test day with noise from the full training records. The full test-day curve over k is
reported as a description, not used for selection.

## 1. Reference totals reproduced from the saved alarms

| set | instances | classic | library alone | combined | combined strict (SE grids: + certification latency) | library vs classic: only library / only classic, exact McNemar |
| --- | --- | --- | --- | --- | --- | --- |
| recorded | 61 | 22/61 | 26/61 | 27/61 | 27/61 | 5 / 1, p = 0.2188 |
| additional (seed 7) | 42 | 13/42 | 17/42 | 21/42 | 21/42 | 8 / 4, p = 0.3877 |
| pooled | 103 | 35/103 | 43/103 | 48/103 | 48/103 | 13 / 5, p = 0.0963 |

## 2. Instances only the combined system detects (classic misses), with the source of the credit

| grid | day | event id | type | source | rules / topology timing | strict first alarm s after start |
| --- | --- | --- | --- | --- | --- | --- |
| 01-Basic | recorded | 11 | industroyer | library | R4@19744 | 6 |
| 01-Basic | recorded | 23 | drift-off | library | R6@37608 | 61 |
| 02-Semiurban | recorded | 7 | control-and-freeze | library | 6490/6612 | 304 |
| 02-Semiurban | recorded | 8 | drift-off | library | 6490/6612 | 69 |
| 02-Semiurban | recorded | 32 | drift-off | library | 33840/33898 | 219 |
| 02-Semiurban | additional (seed 7) | 1 | control-and-freeze | library | 2020/2173 | 22 |
| 02-Semiurban | additional (seed 7) | 4 | drift-off | library | 4700/4856 | 186 |
| 02-Semiurban | additional (seed 7) | 7 | control-and-freeze | library | 4700/4856 | 14 |
| 02-Semiurban | additional (seed 7) | 9 | control-and-freeze | library | 4700/4856 | 11 |
| 02-Semiurban | additional (seed 7) | 13 | drift-off | library | 4700/4856 | 243 |
| 02-Semiurban | additional (seed 7) | 15 | drift-off | library | 4700/4856 | 195 |
| 02-Semiurban | additional (seed 7) | 17 | control-and-freeze | library | 4700/4856 | 14 |
| 02-Semiurban | additional (seed 7) | 20 | control-and-freeze | library | 4700/4856 | 62 |

## 3. Benign exposure and false alarms

| set | source | false alarms per benign record | episodes | benign hours | episodes per hour |
| --- | --- | --- | --- | --- | --- |
| 01-Basic recorded | classic D1 | 0.00059 | 8 | 9.44 | 0.85 |
| 01-Basic recorded | AE | 0.00100 | 9 | 9.44 | 0.95 |
| 01-Basic recorded | library | 0.00124 | 6 | 9.44 | 0.64 |
| 01-Basic recorded | combined | 0.00171 | 10 | 9.44 | 1.06 |
| 02-Semiurban recorded | classic SE-BDD | 0.00000 | 0 | 7.97 | 0.00 |
| 02-Semiurban recorded | library | 0.00017 | 1 | 7.97 | 0.13 |
| 02-Semiurban recorded | library (+cert latency) | 0.00000 | 0 | 7.97 | 0.00 |
| 02-Semiurban recorded | combined | 0.00017 | 1 | 7.97 | 0.13 |
| 03-Rural recorded | classic SE-BDD | 0.00017 | 1 | 7.94 | 0.13 |
| 03-Rural recorded | library | 0.00017 | 1 | 7.94 | 0.13 |
| 03-Rural recorded | library (+cert latency) | 0.00000 | 0 | 7.94 | 0.00 |
| 03-Rural recorded | combined | 0.00017 | 1 | 7.94 | 0.13 |
| 01-Basic additional | classic D1 | 0.00059 | 3 | 2.81 | 1.07 |
| 01-Basic additional | AE | 0.00119 | 3 | 2.81 | 1.07 |
| 01-Basic additional | library | 0.01432 | 22 | 2.81 | 7.82 |
| 01-Basic additional | combined | 0.01491 | 23 | 2.81 | 8.18 |
| 02-Semiurban additional | classic SE-BDD | 0.00000 | 0 | 2.65 | 0.00 |
| 02-Semiurban additional | library | 0.00000 | 0 | 2.65 | 0.00 |
| 02-Semiurban additional | library (+cert latency) | 0.00000 | 0 | 2.65 | 0.00 |
| 02-Semiurban additional | combined | 0.00000 | 0 | 2.65 | 0.00 |

## 4. A/B/C ablation on 02-Semiurban

### recorded

C at k = 1.5 reproduces the stored library alarms: yes. Topologies 13, persistence L = 3, SE-BDD threshold 170.45.

| variant | detected | per type | false alarms per benign record | episodes per benign hour | vs A: only this / only A, McNemar |
| --- | --- | --- | --- | --- | --- |
| A SE-BDD (global threshold) | 7/23 | control-and-freeze 3/5, drift-off 4/9, industroyer 0/9 | 0.00000 | 0.00 |  |
| B per-channel, k = 1.5 | 10/23 | control-and-freeze 4/5, drift-off 6/9, industroyer 0/9 | 0.00401 | 0.50 | 3 / 0, p = 0.250 |
| C per-channel + physics check, k = 1.5 | 10/23 | control-and-freeze 4/5, drift-off 6/9, industroyer 0/9 | 0.00017 | 0.13 | 3 / 0, p = 0.250 |
| B per-channel, k = 10 | 6/23 | control-and-freeze 2/5, drift-off 4/9, industroyer 0/9 | 0.00017 | 0.13 | 1 / 2, p = 1.000 |
| C per-channel + physics check, k = 10 | 6/23 | control-and-freeze 2/5, drift-off 4/9, industroyer 0/9 | 0.00017 | 0.13 | 1 / 2, p = 1.000 |

C minus B at the same k (same candidates, same calibration; only the physics check differs):

| k | detected (C - B) | instances whose outcome changed | false alarms per record (C - B) | episodes per hour (C - B) |
| --- | --- | --- | --- | --- |
| 1.5 | +0 | none | -0.00384 | -0.38 |
| 10 | +0 | none | +0.00000 | +0.00 |

Matched budget, chosen on calibration data only (target 0.5 false-alarm episodes per hour on the second half of the training records, noise from the first half): B: k = 10.0; C: k = 10.0.

Calibration curves (episodes per hour on the calibration half, by k): B: 1:6.67, 1.25:3.83, 1.5:4.00, 2:3.17, 2.5:2.33, 3:2.67, 4:1.83, 5:1.67, 7:1.00, 10:0.33, 15:0.17, 20:0.00; C: 1:5.33, 1.25:3.83, 1.5:3.33, 2:2.50, 2.5:2.33, 3:2.67, 4:1.83, 5:1.67, 7:1.00, 10:0.33, 15:0.17, 20:0.00

Test-day curve over k (description only, not used to choose anything):

| day | variant | k | detected | false alarms per record | episodes per hour |
| --- | --- | --- | --- | --- | --- |
| recorded | B | 1.0 | 14/23 | 0.19160 | 3.01 |
| recorded | C | 1.0 | 11/23 | 0.01656 | 1.51 |
| recorded | B | 1.25 | 10/23 | 0.00662 | 0.88 |
| recorded | C | 1.25 | 10/23 | 0.00052 | 0.38 |
| recorded | B | 1.5 | 10/23 | 0.00401 | 0.50 |
| recorded | C | 1.5 | 10/23 | 0.00017 | 0.13 |
| recorded | B | 2.0 | 10/23 | 0.00174 | 0.38 |
| recorded | C | 2.0 | 10/23 | 0.00017 | 0.13 |
| recorded | B | 2.5 | 10/23 | 0.00070 | 0.25 |
| recorded | C | 2.5 | 10/23 | 0.00017 | 0.13 |
| recorded | B | 3.0 | 9/23 | 0.00017 | 0.13 |
| recorded | C | 3.0 | 9/23 | 0.00017 | 0.13 |
| recorded | B | 4.0 | 9/23 | 0.00017 | 0.13 |
| recorded | C | 4.0 | 9/23 | 0.00017 | 0.13 |
| recorded | B | 5.0 | 8/23 | 0.00017 | 0.13 |
| recorded | C | 5.0 | 8/23 | 0.00017 | 0.13 |
| recorded | B | 7.0 | 6/23 | 0.00017 | 0.13 |
| recorded | C | 7.0 | 6/23 | 0.00017 | 0.13 |
| recorded | B | 10.0 | 6/23 | 0.00017 | 0.13 |
| recorded | C | 10.0 | 6/23 | 0.00017 | 0.13 |
| recorded | B | 15.0 | 5/23 | 0.00017 | 0.13 |
| recorded | C | 15.0 | 5/23 | 0.00017 | 0.13 |
| recorded | B | 20.0 | 5/23 | 0.00000 | 0.00 |
| recorded | C | 20.0 | 5/23 | 0.00000 | 0.00 |

Channels whose margin the physics check raised above 1.5 x noise, per topology (median ratio proved margin / (1.5 x noise)):

| topology | channels raised | median ratio |
| --- | --- | --- |
| ties=none;out=L20+L113+L114+L115+L116+L117+L119+L120 | 232 | 2.46 |
| ties=none;out=L20+L72+L113+L114+L115+L116+L117+L119+L120 | 226 | 2.31 |
| ties=none;out=L20+L114+L115+L116+L117+L119+L120 | 232 | 2.46 |
| ties=none;out=L20+L53+L114+L115+L116+L117+L119+L120 | 232 | 2.48 |
| ties=none;out=L20+L44+L53+L114+L115+L116+L117+L119+L120 | 229 | 2.46 |
| ties=none;out=L20+L53+L109+L115+L116+L117+L119+L120 | 231 | 2.46 |
| ties=none;out=L53+L88+L109+L115+L116+L117+L119+L120 | 231 | 2.45 |
| ties=none;out=L20+L53+L109+L115+L116+L117+L120 | 232 | 2.42 |
| ties=none;out=L20+L53+L109+L115+L116+L117 | 246 | 2.43 |
| ties=none;out=L20+L42+L53+L109+L115+L116+L117 | 233 | 2.41 |
| ties=none;out=L42+L53+L109+L115+L116+L117 | 240 | 2.56 |
| ties=none;out=L4+L7+L42+L53+L109+L115+L116+L117 | 231 | 2.50 |
| ties=none;out=L4+L7+L21+L42+L53+L109+L115+L116+L117 | 204 | 2.19 |
### additional (seed 7)

C at k = 1.5 reproduces the stored library alarms: yes. Topologies 7, persistence L = 3, SE-BDD threshold 138.18.

| variant | detected | per type | false alarms per benign record | episodes per benign hour | vs A: only this / only A, McNemar |
| --- | --- | --- | --- | --- | --- |
| A SE-BDD (global threshold) | 2/21 | control-and-freeze 1/7, drift-off 1/7, industroyer 0/7 | 0.00000 | 0.00 |  |
| B per-channel, k = 1.5 | 14/21 | control-and-freeze 7/7, drift-off 6/7, industroyer 1/7 | 0.09314 | 5.65 | 12 / 0, p = 0.000 |
| C per-channel + physics check, k = 1.5 | 10/21 | control-and-freeze 6/7, drift-off 4/7, industroyer 0/7 | 0.00000 | 0.00 | 8 / 0, p = 0.008 |
| B per-channel, k = 4 | 11/21 | control-and-freeze 7/7, drift-off 4/7, industroyer 0/7 | 0.03977 | 3.01 | 9 / 0, p = 0.004 |
| C per-channel + physics check, k = 4 | 10/21 | control-and-freeze 6/7, drift-off 4/7, industroyer 0/7 | 0.00000 | 0.00 | 8 / 0, p = 0.008 |

C minus B at the same k (same candidates, same calibration; only the physics check differs):

| k | detected (C - B) | instances whose outcome changed | false alarms per record (C - B) | episodes per hour (C - B) |
| --- | --- | --- | --- | --- |
| 1.5 | -4 | 2, 12, 18, 19 | -0.09314 | -5.65 |
| 4 | -1 | 12 | -0.03977 | -3.01 |

Matched budget, chosen on calibration data only (target 0.5 false-alarm episodes per hour on the second half of the training records, noise from the first half): B: k = 4.0; C: k = 4.0.

Calibration curves (episodes per hour on the calibration half, by k): B: 1:6.66, 1.25:2.33, 1.5:1.33, 2:1.00, 2.5:2.00, 3:0.67, 4:0.33, 5:0.00, 7:0.00, 10:0.00, 15:0.00, 20:0.00; C: 1:3.66, 1.25:1.67, 1.5:1.00, 2:1.00, 2.5:2.00, 3:0.67, 4:0.33, 5:0.00, 7:0.00, 10:0.00, 15:0.00, 20:0.00

Test-day curve over k (description only, not used to choose anything):

| day | variant | k | detected | false alarms per record | episodes per hour |
| --- | --- | --- | --- | --- | --- |
| additional (seed 7) | B | 1.0 | 15/21 | 0.15228 | 7.91 |
| additional (seed 7) | C | 1.0 | 11/21 | 0.00052 | 0.38 |
| additional (seed 7) | B | 1.25 | 14/21 | 0.12873 | 5.65 |
| additional (seed 7) | C | 1.25 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 1.5 | 14/21 | 0.09314 | 5.65 |
| additional (seed 7) | C | 1.5 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 2.0 | 12/21 | 0.06175 | 4.14 |
| additional (seed 7) | C | 2.0 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 2.5 | 12/21 | 0.05390 | 3.39 |
| additional (seed 7) | C | 2.5 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 3.0 | 11/21 | 0.04762 | 3.01 |
| additional (seed 7) | C | 3.0 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 4.0 | 11/21 | 0.03977 | 3.01 |
| additional (seed 7) | C | 4.0 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 5.0 | 11/21 | 0.03035 | 3.01 |
| additional (seed 7) | C | 5.0 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 7.0 | 10/21 | 0.01518 | 1.88 |
| additional (seed 7) | C | 7.0 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 10.0 | 10/21 | 0.00523 | 1.13 |
| additional (seed 7) | C | 10.0 | 10/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 15.0 | 8/21 | 0.00000 | 0.00 |
| additional (seed 7) | C | 15.0 | 8/21 | 0.00000 | 0.00 |
| additional (seed 7) | B | 20.0 | 8/21 | 0.00000 | 0.00 |
| additional (seed 7) | C | 20.0 | 8/21 | 0.00000 | 0.00 |

Channels whose margin the physics check raised above 1.5 x noise, per topology (median ratio proved margin / (1.5 x noise)):

| topology | channels raised | median ratio |
| --- | --- | --- |
| ties=none;out=L21+L71+L113+L114+L115+L116+L119+L120 | 290 | 6.32 |
| ties=none;out=L21+L71+L79+L113+L114+L115+L116+L119+L120 | 280 | 6.08 |
| ties=none;out=L21+L71+L113+L114+L115+L119+L120 | 303 | 6.22 |
| ties=none;out=L21+L71+L80+L113+L114+L115+L119+L120 | 289 | 6.26 |
| ties=none;out=L21+L52+L71+L80+L113+L114+L115+L119+L120 | 284 | 6.24 |
| ties=none;out=L21+L44+L71+L80+L113+L114+L115+L119+L120 | 284 | 6.25 |
| ties=none;out=L21+L71+L80+L104+L113+L114+L115+L119+L120 | 257 | 5.88 |
