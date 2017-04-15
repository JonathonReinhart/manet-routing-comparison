#!/usr/bin/env python
#
# Jonathon Reinhart
# University of Dayton
# ECE-595: Computer Networks
# Spring 2017
#
# References:
# - https://www.nsnam.org/doxygen/manet-routing-compare_8cc.html
# - https://www.nsnam.org/doxygen/simple-routing-ping6_8py.html 
# - https://www.nsnam.org/doxygen/main-grid-topology_8cc_source.html
#
import argparse
import logging

import ns.applications
import ns.core
from ns.core import DoubleValue, StringValue, UintegerValue, Seconds
import ns.internet
import ns.network
import ns.wifi
import ns.mobility
import ns.aodv
import ns.olsr
import ns.dsdv

import readline
import rlcompleter

WIFI_TX_POWER       = 7.5   # dBm
NODE_X_INTERVAL     = 5.0   # m
NODE_Y_INTERVAL     = 20.0  # m
NODES_PER_ROW       = 20
NUM_SINKS           = 10
UDP_PORT            = 9
TOTAL_TIME          = 200.0 # sec

class ManetSimulator(object):
    def __init__(self, num_nodes, protocol):
        self._setup(num_nodes, protocol)


    def _setup(self, num_nodes, protocol):
        # Create a container with the desired number of nodes
        self.nodes = ns.network.NodeContainer();
        self.nodes.Create(num_nodes)

        # Set up Wifi devices
        phyMode = StringValue("DsssRate11Mbps")

        wifi = ns.wifi.WifiHelper()
        wifi.SetStandard(ns.wifi.WIFI_PHY_STANDARD_80211b)
        wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                     "DataMode", phyMode,
                                     "ControlMode", phyMode)

        wifiPhy = self._setup_wifi_phy()
        wifiMac = self._setup_wifi_mac()
        adhocDevices = wifi.Install(wifiPhy, wifiMac, self.nodes)

        # Set up mobility
        mobility = self._setup_mobility()
        mobility.Install(self.nodes)

        # Set up routing
        inet = self._setup_routing(protocol)
        inet.Install(self.nodes)

        # Assign IP addresses
        addrs = ns.internet.Ipv4AddressHelper()
        addrs.SetBase(
            ns.network.Ipv4Address("10.1.1.0"),
            ns.network.Ipv4Mask("255.255.255.0"))
        ifaces = addrs.Assign(adhocDevices)

        onoff = ns.applications.OnOffHelper("ns3::UdpSocketFactory", ns.network.Address())
        onoff.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1.0]"))
        onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0.0]"))

        # Set up the source/sink nodes
        for i in xrange(NUM_SINKS):
            node = self.nodes.Get(i)
            sockaddr = ns.network.InetSocketAddress(ifaces.GetAddress(i), UDP_PORT)

            self._setup_packet_receive(sockaddr, node)

            onoff.SetAttribute("Remote", ns.network.AddressValue(sockaddr))
            temp = onoff.Install(self.nodes.Get(i + NUM_SINKS))

            var = ns.core.UniformRandomVariable()
            temp.Start(Seconds(var.GetValue(100.0, 101.0)))
            temp.Stop(Seconds(TOTAL_TIME))


    def _setup_wifi_phy(self):
        chanhlp = ns.wifi.YansWifiChannelHelper()
        chanhlp.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel")
        chanhlp.AddPropagationLoss("ns3::FriisPropagationLossModel")

        phy = ns.wifi.YansWifiPhyHelper.Default()
        phy.SetChannel(chanhlp.Create())

        txp = DoubleValue(WIFI_TX_POWER)
        phy.Set("TxPowerStart", txp)
        phy.Set("TxPowerEnd", txp)

        return phy

    def _setup_wifi_mac(self):
        """Set up non-QoS MAC"""
        mac = ns.wifi.NqosWifiMacHelper.Default()
        mac.SetType("ns3::AdhocWifiMac")
        return mac

    def _setup_mobility(self):
        mobility = ns.mobility.MobilityHelper()

        # Set up the grid
        # Objects are layed out starting from (-100, -100)
        mobility.SetPositionAllocator(
                "ns3::GridPositionAllocator",
                "MinX", DoubleValue(-100.0),
                "MinY", DoubleValue(-100.0),
                "DeltaX", DoubleValue(NODE_X_INTERVAL),
                "DeltaY", DoubleValue(NODE_Y_INTERVAL),
                "GridWidth", UintegerValue(NODES_PER_ROW),
                "LayoutType", StringValue("RowFirst"),
                )

        # Objects will be in a fixed position throughout the simulation
        mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel")

        return mobility

    def _setup_routing(self, protocol_name):
        protocol = protocol_map[protocol_name]()
        route_list = ns.internet.Ipv4ListRoutingHelper()
        route_list.Add(protocol, 100)

        inet = ns.internet.InternetStackHelper()
        inet.SetRoutingHelper(route_list)
        return inet

    def _setup_packet_receive(self, sockaddr, node):
        tid = ns.core.TypeId.LookupByName("ns3::UdpSocketFactory")
        sink = ns.network.Socket.CreateSocket(node, tid)
        sink.Bind(sockaddr)
        sink.SetRecvCallback(self._packet_rx_callback)
        return sink

    def _packet_rx_callback(self, *args, **kwargs):
        logging.debug("Packet callback: args={} kwargs={}".format(args, kwargs))


protocol_map = {
    'AODV':     ns.aodv.AodvHelper,
    'OLSR':     ns.olsr.OlsrHelper,
    'DSDV':     ns.dsdv.DsdvHelper,
}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', '--num-nodes', type=int, default=20,
            help='Number of nodes (default: %(default)d)')
    ap.add_argument('-p', '--protocol', default='OLSR', choices=protocol_map.keys(),
            help='Routing protocol (default: %(default)s)')
    ap.add_argument('-l', '--log', dest='loglevel',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            default='WARNING',
            help='Set the logging level (default: %(default)s)')

    return ap.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=args.loglevel)

    sim = ManetSimulator(
            num_nodes = args.num_nodes,
            protocol = args.protocol,
            )


    trace = ns.network.AsciiTraceHelper()
    ns.mobility.MobilityHelper.EnableAsciiAll(trace.CreateFileStream("trace.mob"))


    ns.core.Simulator.Stop(Seconds(TOTAL_TIME))
    ns.core.Simulator.Run()


    #readline.parse_and_bind('tab: complete')
    #import code; code.interact(local=locals())

if __name__ == '__main__':
    main()
