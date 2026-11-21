# Provenance of the 01-Basic rule library

Inputs: the provenance replay `scripts/14_consolidation.py --causal --provenance --tag _prov` (same recording,
detectors D1 and AE, parameters and chronology as the reference run _causal), its structured log
(data/interim/provenance_prov_sherlock.pkl), the per-record detector alarms, and, for evaluation only, the
attack labels. For each rule: source episode, its window and the attack (if any) whose window contains it,
the inputs used to build the rule and where each component came from, timing, later opportunities, firing,
and whether the rule changed the system's decision (an attack detected by the rule and by no detector and no
other active rule). For the two credited rules: ablation (rule removed at scoring time, everything else kept)
and the false-alarm episodes the rule added. Counterfactual for G rules: the same topology, model, noise and
template with a seed that does not depend on the episode, certified and evaluated from the same activation
time. Also the five injected days (causal runs), without provenance log, for firing and decisive credit.

Replay reproduces the reference library (_causal: same rule names and per-record firing): yes.

## 1. Traceability (s from the start of the test day)

| rule | family | episode # | source alert start | labelled attack containing the source (evaluation only) | topology of the alert window | synthesis window end | synthesis + certification done | calibration done | acts from | later process attacks | opportunities (G: in its topology) | fired in | decisive in (no detector, no other rule) | earlier than detectors in | content | where the content came from |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S-line 2 out+line 3 out+load_p.2 to zero+l | S | 0 | 4293 | 0 (industroyer) | outside envelope | 4353 | 4387 |  | 4387 | 15 | 15 | - | - | - | line_in.2: 1.000 -> 0.000; line_in.3: 1.000 -> 0.000; load_p.2: 0.101 -> 0.000; load_p.3: 0.170 -> 0.000; load_p.4: 0.128 -> 0.000; sgen_p.1: 0.020 -> 0.000; sgen_p.2: 0.030 -> 0.000; sgen_p.3: 0.030 -> 0.000; sgen_p.9: 0.033 -> 0.000; storage_p.0: 0.600 -> 0.000 | event: every atom (which lines went out, which injections dropped to zero) is read from the medians 40-10 s before the alert and in the 60 s alert window; thresholds (0.5 for line state, 1 % of scale for injections) are template |
| G@ties=none;out=none;tap=0,0 | G | 1 | 4505 | 0 (industroyer) | ties=none;out=none;tap=0,0 | 4565 | 4599 |  | 4599 | 15 | 3 | 1,4 | - | 4 | topology ties=none;out=none;tap=0,0; 29 quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; margin from train noise on 26, from physics bound on 3; median margin 0.0072 pu (voltage) | event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound |
| G@ties=S2;out=L4;tap=0,0 | G | 5 | 14729 | 5 (benign event) (control center) | ties=S2;out=L4;tap=0,0 | 14789 | 14819 |  | 14819 | 12 | 1 | 7 | - | - | topology ties=S2;out=L4;tap=0,0; 28 quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; margin from train noise on 24, from physics bound on 4; median margin 0.0072 pu (voltage) | event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound |
| S-line 3 out+load_p.3 to zero+sgen_p.2 to  | S | 7 | 17737 | 7 (industroyer) | outside envelope | 17797 | 17804 |  | 17804 | 11 | 11 | - | - | - | line_in.3: 1.000 -> 0.000; load_p.3: 0.506 -> 0.000; sgen_p.2: 0.030 -> 0.000; sgen_p.9: 0.033 -> 0.000 | event: every atom (which lines went out, which injections dropped to zero) is read from the medians 40-10 s before the alert and in the 60 s alert window; thresholds (0.5 for line state, 1 % of scale for injections) are template |
| G@ties=S1+S2;out=L4+L11;tap=0,0 | G | 9 | 19744 | 8 (benign event) (control center) | ties=S1+S2;out=L4+L11;tap=0,0 | 19804 | 19867 |  | 19867 | 11 | 7 | 9,10,11,13,14,17 | 11 | 13,17 | topology ties=S1+S2;out=L4+L11;tap=0,0; 27 quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; margin from train noise on 15, from physics bound on 12; median margin 0.0110 pu (voltage) | event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound |
| G@ties=S1+S2;out=L11;tap=0,0 | G | 15 | 35530 | 19 (arp-spoof) | ties=S1+S2;out=L11;tap=0,0 | 35590 | 35668 |  | 35668 | 3 | 1 | - | - | - | topology ties=S1+S2;out=L11;tap=0,0; 28 quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; margin from train noise on 18, from physics bound on 10; median margin 0.0079 pu (voltage) | event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound |
| G@ties=S1+S2;out=L11;tap=-1,0 | G | 17 | 37608 | 21 (benign event) (control center) | ties=S1+S2;out=L11;tap=-1,0 | 37668 | 37695 |  | 37695 | 2 | 2 | 23 | 23 | - | topology ties=S1+S2;out=L11;tap=-1,0; 28 quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; margin from train noise on 23, from physics bound on 5; median margin 0.0072 pu (voltage) | event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound |
| G@ties=S1+S2;out=L9;tap=0,0 | G | 19 | 41578 | 25 (benign event) (control center) | ties=S1+S2;out=L9;tap=0,0 | 41638 | 41669 |  | 41669 | 0 | 0 | - | - | - | topology ties=S1+S2;out=L9;tap=0,0; 28 quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; margin from train noise on 22, from physics bound on 6; median margin 0.0072 pu (voltage) | event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound |
| G@ties=S1+S2+S3;out=L7+L9;tap=0,0 | G | 20 | 41846 | 26 (benign event) (control center) | ties=S1+S2+S3;out=L7+L9;tap=0,0 | 41906 | 41951 |  | 41951 | 0 | 0 | - | - | - | topology ties=S1+S2+S3;out=L7+L9;tap=0,0; 27 quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; margin from train noise on 22, from physics bound on 5; median margin 0.0072 pu (voltage) | event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound |
| G@ties=S1+S2+S3;out=L8+L9;tap=0,0 | G | 21 | 42739 | 27 (benign event) (control center) | ties=S1+S2+S3;out=L8+L9;tap=0,0 | 42799 | 42826 |  | 42826 | 0 | 0 | - | - | - | topology ties=S1+S2+S3;out=L8+L9;tap=0,0; 27 quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; margin from train noise on 22, from physics bound on 5; median margin 0.0072 pu (voltage) | event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound |

## 2. Alert episodes covered by an existing rule (no new synthesis)

| episode start | labelled attack containing it | covering rule(s) |
| --- | --- | --- |
| 6011 | 1 (drift-off) | G@ties=none;out=none;tap=0,0 |
| 11562 | 4 (control-and-freeze) | G@ties=none;out=none;tap=0,0 |
| 12225 | no labelled event (benign period) | G@ties=none;out=none;tap=0,0 |
| 18008 | 7 (industroyer) | G@ties=S2;out=L4;tap=0,0 |
| 20930 | 9 (drift-off) | G@ties=S1+S2;out=L4+L11;tap=0, |
| 26740 | 13 (control-and-freeze) | G@ties=S1+S2;out=L4+L11;tap=0, |
| 28655 | 14 (drift-off) | G@ties=S1+S2;out=L4+L11;tap=0, |
| 31675 | 17 (control-and-freeze) | G@ties=S1+S2;out=L4+L11;tap=0, |
| 40028 | 24 (benign event) (control center) | G@ties=S1+S2;out=L11;tap=0,0 |

## 3. Ablation of the decisive rule at scoring time

| attack | type | rule | first alarm with the rule | without the rule (detectors D1, AE and all other rules kept) |
| --- | --- | --- | --- | --- |
| 11 | industroyer | G@ties=S1+S2;out=L4+L11;tap=0,0 | 6 s (this rule) | missed |
| 23 | drift-off | G@ties=S1+S2;out=L11;tap=-1,0 | 61 s (this rule) | missed |

## 4. False-alarm episodes per rule after activation (benign records)

| rule | episodes | episodes with no detector alarm | benign hours active | benign hours active in its topology |
| --- | --- | --- | --- | --- |
| S-line 2 out+line 3 out+load_p.2 to zero+l | 0 | 0 | 8.26 | 8.26 |
| G@ties=none;out=none;tap=0,0 | 1 | 1 | 8.26 | 2.36 |
| G@ties=S2;out=L4;tap=0,0 | 0 | 0 | 5.87 | 1.17 |
| S-line 3 out+load_p.3 to zero+sgen_p.2 to  | 0 | 0 | 5.16 | 5.16 |
| G@ties=S1+S2;out=L4+L11;tap=0,0 | 0 | 0 | 4.66 | 2.24 |
| G@ties=S1+S2;out=L11;tap=0,0 | 1 | 1 | 1.59 | 0.75 |
| G@ties=S1+S2;out=L11;tap=-1,0 | 0 | 0 | 1.25 | 0.36 |
| G@ties=S1+S2;out=L9;tap=0,0 | 0 | 0 | 0.43 | 0.04 |
| G@ties=S1+S2+S3;out=L7+L9;tap=0,0 | 0 | 0 | 0.35 | 0.22 |
| G@ties=S1+S2+S3;out=L8+L9;tap=0,0 | 0 | 0 | 0.10 | 0.10 |

## 5. Counterfactual G rules: same topology, model, noise and template, seed independent of the episode, same activation time

| rule | same seed rebuilds the identical candidate | counterfactual verdict | margins that differ | largest relative margin difference | original fired in | counterfactual fired in | original decisive in | counterfactual decisive in | false-alarm episodes original / counterfactual |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G@ties=none;out=none;tap=0,0 | yes | certified | 4/29 | 15.10 % | 1,4 | 1,4 | - | - | 1 / 1 |
| G@ties=S2;out=L4;tap=0,0 | yes | certified | 8/28 | 9.96 % | 7 | 7 | - | - | 0 / 0 |
| G@ties=S1+S2;out=L4+L11;tap=0,0 | yes | certified | 12/27 | 35.93 % | 9,10,11,13,14,17 | 9,10,11,13,14,17 | 11 | 11 | 0 / 0 |
| G@ties=S1+S2;out=L11;tap=0,0 | yes | certified | 11/28 | 33.80 % | - | - | - | - | 1 / 1 |
| G@ties=S1+S2;out=L11;tap=-1,0 | yes | certified | 6/28 | 44.30 % | 23 | 23 | 23 | 23 | 0 / 0 |
| G@ties=S1+S2;out=L9;tap=0,0 | yes | certified | 6/28 | 14.69 % | - | - | - | - | 0 / 0 |
| G@ties=S1+S2+S3;out=L7+L9;tap=0,0 | yes | certified | 5/27 | 19.73 % | - | - | - | - | 0 / 0 |
| G@ties=S1+S2+S3;out=L8+L9;tap=0,0 | yes | certified | 5/27 | 36.36 % | - | - | - | - | 0 / 0 |

## 6. Injected days (causal runs): firing and decisive credit per rule

| seed | rule | later attacks | fired in | decisive in |
| --- | --- | --- | --- | --- |
| 7 | G@ties=S2;out=L5;tap=0,0 | 18 | - | - |
| 7 | G@ties=S2+S3;out=L5+L8;tap=0,0 | 17 | 4,6,8,9,11,13 | - |
| 8 | G@ties=S2;out=L5;tap=0,0 | 18 | - | - |
| 8 | G@ties=S2+S3;out=L5+L8;tap=0,0 | 17 | 5,8,10,13 | - |
| 9 | G@ties=S2;out=L5;tap=0,0 | 21 | 4 | - |
| 9 | G@ties=S2+S3;out=L5+L8;tap=0,0 | 19 | 5,6,7,8,10,11,12,13 | - |
| 10 | G@ties=S2;out=L5;tap=0,0 | 21 | 3 | - |
| 10 | G@ties=S2+S3;out=L5+L8;tap=0,0 | 18 | 5,6,8,10,13,14 | - |
| 11 | G@ties=S2;out=L5;tap=0,0 | 21 | 1,3 | - |
| 11 | G@ties=S2+S3;out=L5+L8;tap=0,0 | 18 | 5,7,8,10,11 | - |
