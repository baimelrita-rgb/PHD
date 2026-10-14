# OpTC label audit (optc_redteam.csv only; no raw flows)

Rows: 1359 (unique ids: 1359). Labels: {'Other': 1110, 'Lateral movement': 249}.
Days that have any labeled row: [1, 2] (Day 3 has none in this file).

## Flows by kind and label

| kind | Lateral movement | Other |
|---|---:|---:|
| failed_hop | 6 | 0 |
| fanout | 200 | 0 |
| hop | 41 | 0 |
| malicious_process | 2 | 548 |
| ping_sweep | 0 | 562 |

Lateral-movement flows: 249; of them fan-out (one host to many targets): 200 (80%). By day: {1: 140, 2: 60}.

## Documented hop edges

| day | src | dst | method | kind | label | flows |
|---|---|---|---|---|---|---:|
| 1 | SysClient0201 | 142.20.56.204 | SMB | hop | Lateral movement | 6 |
| 1 | SysClient0201 | SysClient0402 | invoke_wmi | hop | Lateral movement | 5 |
| 1 | SysClient0402 | SysClient0660 | invoke_wmi | hop | Lateral movement | 3 |
| 1 | SysClient0660 | DC1 | invoke_wmi | hop | Lateral movement | 4 |
| 2 | DC1 | SysClient0501 | WMI | failed_hop | Lateral movement | 4 |
| 2 | DC1 | SysClient0501 | WMI | hop | Lateral movement | 10 |
| 2 | DC1 | SysClient0502 | WMI | failed_hop | Lateral movement | 2 |
| 2 | SysClient0501 | DC1 | unknown method | hop | Lateral movement | 9 |
| 2 | SysClient0501 | SysClient0974 | RDP | hop | Lateral movement | 2 |
| 2 | SysClient0974 | SysClient0005 | RDP | hop | Lateral movement | 2 |

Longest successful hop chain per day: {1: 3, 2: 3}.

## Pending (needs the raw FLOW START events joined on `id`)

- timestamps of every labeled flow, hence first-compromise time per host;
- the destinations hidden behind 'multiple targets / hosts' (the fan-out rows);
- the number of distinct compromised hosts per day;
- the benign graph (nodes, windows, base rate) for the train/test design.
