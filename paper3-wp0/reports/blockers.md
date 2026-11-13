# Blockers

1. G1: the Sherlock 01-Basic download has no grid model file (no pandapower net, no Wattson grid definition; `sherlock-config.yml` only names the scenario `cigre-mv`). Not worked around with mirrors. T7 instead tests a reconstruction from pandapower's CIGRE MV (all DER) using only data in the download. Fetching the original Wattson scenario needs owner approval.
2. Transformer tap changer parameters are missing from both the pandapower CIGRE MV model and the Sherlock download. In the reference envelope, taps stay fixed. In T7, the 6 of 106 scanned snapshots with a nonzero tap were excluded.
3. Sherlock switch indices 8 to 31 have no documented mapping. The mapping used (switch 8+2l = line l from end, 9+2l = to end) was inferred from the data and checked on 172 of 172 open switches.
