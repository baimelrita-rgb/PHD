import pandapower as pp
from p3 import envelope as E


def test_pandapower_powerflow_converges():
    net = E.build_net()
    pp.runpp(net)
    assert net.converged
    assert 0.9 < net.res_bus.vm_pu.min() < 1.1


def test_configs_radial_and_connected():
    import networkx as nx
    cfgs = E.enumerate_configs()
    assert cfgs[0] == E.base_config()
    for c in cfgs:
        net = E.apply_config(E.base_net(), c)
        assert nx.is_tree(E.topology_graph(net))
