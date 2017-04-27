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
# - http://personal.ee.surrey.ac.uk/Personal/K.Katsaros/media/ns3lab-sol/lab-4-solved.cc
# - https://www.nsnam.org/docs/models/html/flow-monitor.html
# - https://www.nsnam.org/doxygen/wifi-olsr-flowmon_8py_source.html
#
# - AODV:
#   - https://www.nsnam.org/docs/models/html/aodv.html
#   - https://www.nsnam.org/doxygen/classns3_1_1_aodv_helper.html
#   - https://www.nsnam.org/doxygen/classns3_1_1aodv_1_1_routing_protocol.html
#
# TODO:
# - Determine and record routing establishment time
# - Determine and record end-to-end delay
#
from __future__ import print_function
import argparse
import logging
import random
import math
import csv

import ns.applications
import ns.core
from ns.core import BooleanValue, DoubleValue, StringValue, UintegerValue, Seconds, TimeValue
import ns.internet
import ns.network
import ns.wifi
import ns.mobility
import ns.aodv
import ns.olsr
import ns.dsdv
import ns.flow_monitor
import ns.visualizer

# At 7.5 dBm, nodes should be about 80 m apart to ensure that one node's
# transmissions can only reach his immediate neighbors. This was determined
# empircally by putting nodes in a straight line, and looking at the packet
# captures.

WIFI_TX_POWER       = 7.5   # dBm
UDP_PORT            = 9
TOTAL_TIME          = 200.0 # sec
UDP_SEND_START_TIME = 15.0  # sec
UDP_PACKET_SIZE     = 256   # bytes
UDP_PACKET_INTERVAL = 0.1   # sec

def SelectRandomNode(nodes, k=1):
    """Select 'k' random nodes from the NodeContainer 'nodes'"""
    indices = random.sample(xrange(nodes.GetN()), k)
    return [nodes.Get(i) for i in indices]


class ManetSimulator(object):
    def __init__(self, num_nodes, node_spacing, node_placement, protocol):
        self._setup(num_nodes, node_spacing, node_placement, protocol)

        self._bytesTotal = 0
        self._bytesLast= 0
        self._packetsTotal  = 0
        self._packetsLast= 0

        self._csvfile = open('throughput.csv', 'wb')
        self._csvwriter = csv.DictWriter(self._csvfile,
                fieldnames = ['time', 'bytes', 'bytes_per_sec', 'packets', 'packets_per_sec'])
        self._csvwriter.writeheader()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def close(self):
        if self._csvfile:
            self._csvfile.close()


    def _setup(self, num_nodes, node_spacing, node_placement, protocol):
        # Create a container with the desired number of nodes
        self.nodes = ns.network.NodeContainer();
        self.nodes.Create(num_nodes)

        # Set up Wifi devices
        adhocDevices = self._setup_wifi()

        # Set up mobility
        self._setup_mobility(num_nodes, node_spacing, node_placement)

        # Set up routing
        self._setup_routing(protocol)

        # Assign IP addresses
        addrs = ns.internet.Ipv4AddressHelper()
        addrs.SetBase(
            ns.network.Ipv4Address("10.1.1.0"),
            ns.network.Ipv4Mask("255.255.255.0"))
        ifaces = addrs.Assign(adhocDevices)

        # Randomly choose origin node (O) and destination node (D)
        #self.origin, self.destination = SelectRandomNode(self.nodes, 2)
        self.origin = self.nodes.Get(0)
        self.destination = self.nodes.Get(self.nodes.GetN() - 1)

        # Set up the sink node
        node = self.destination
        self._server_sockaddr = ns.network.InetSocketAddress(
                ifaces.GetAddress(node.GetId()), UDP_PORT)
        self._setup_packet_receive(self._server_sockaddr, node)

        # Source node
        client = ns.applications.UdpClientHelper(
                self._server_sockaddr.GetIpv4(),
                self._server_sockaddr.GetPort())
        client.SetAttribute("MaxPackets", UintegerValue(0xFFFFFFFF))
        client.SetAttribute("Interval", TimeValue(Seconds(UDP_PACKET_INTERVAL)))
        client.SetAttribute("PacketSize", UintegerValue(UDP_PACKET_SIZE))
        app = client.Install(ns.network.NodeContainer(self.origin))
        app.Start(Seconds(0))
        app.Stop(Seconds(TOTAL_TIME))


        self._setup_flowmon()

    def _setup_wifi(self):
        phyMode = StringValue("DsssRate11Mbps")

        wifi = ns.wifi.WifiHelper()
        wifi.SetStandard(ns.wifi.WIFI_PHY_STANDARD_80211b)
        wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                     "DataMode", phyMode,
                                     "ControlMode", phyMode,
                                     "NonUnicastMode", phyMode)

        wifiPhy = self._setup_wifi_phy()
        wifiMac = self._setup_wifi_mac()
        devices = wifi.Install(wifiPhy, wifiMac, self.nodes)

        # Enable tracing
        wifiPhy.EnablePcapAll("manet", promiscuous=True)

        return devices


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

    def _setup_mobility(self, num_nodes, node_spacing, node_placement):
        mobility = ns.mobility.MobilityHelper()

        if node_placement == 'straight-line':
            grid_width = 1
        elif node_placement == 'grid':
            # Try to keep the layout as square as possible
            grid_width = int(round(math.sqrt(num_nodes)))
        else:
            raise ValueError("Invalid node_placement")

        # Set up the grid
        # Objects are layed out starting from (-100, -100)
        mobility.SetPositionAllocator(
                "ns3::GridPositionAllocator",
                "MinX", DoubleValue(0),
                "MinY", DoubleValue(0),
                "DeltaX", DoubleValue(node_spacing),
                "DeltaY", DoubleValue(node_spacing),
                "GridWidth", UintegerValue(grid_width),
                "LayoutType", StringValue("RowFirst"),
                )

        # Objects will be in a fixed position throughout the simulation
        mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel")
        mobility.Install(self.nodes)

        # Enable tracing
        trace = ns.network.AsciiTraceHelper()
        mobility.EnableAsciiAll(trace.CreateFileStream("trace.mob"))

    def _setup_routing(self, protocol_name):
        inet = ns.internet.InternetStackHelper()

        if True:
            protocol = protocol_map[protocol_name]()
            route_list = ns.internet.Ipv4ListRoutingHelper()
            route_list.Add(protocol, 100)
            inet.SetRoutingHelper(route_list)

        inet.Install(self.nodes)

    def _setup_packet_receive(self, sockaddr, node):
        tid = ns.core.TypeId.LookupByName("ns3::UdpSocketFactory")
        sink = ns.network.Socket.CreateSocket(node, tid)
        sink.Bind(sockaddr)
        sink.SetRecvCallback(self._packet_rx_callback)

    def _packet_rx_callback(self, socket):
        while True:
            packet = socket.Recv()
            if not packet:
                return
            self._bytesTotal    += packet.GetSize()
            self._bytesLast     += packet.GetSize()
            self._packetsTotal  += 1
            self._packetsLast   += 1

    def _setup_flowmon(self):
        # Set up FlowMonitor
        self.flowmon_helper = ns.flow_monitor.FlowMonitorHelper()
        self.flowmon_helper.InstallAll()

    def check_throughput(self):
        interval = 1.0  # sec

        self._csvwriter.writerow(dict(
            time = ns.core.Simulator.Now().GetSeconds(),
            bytes = self._bytesTotal,
            bytes_per_sec = self._bytesLast / interval,
            packets = self._packetsTotal,
            packets_per_sec = self._packetsLast / interval,
            ))

        logging.debug("t={} Bytes: total={}, {}/sec    Packets: total={}, {}/sec".format(
            ns.core.Simulator.Now().GetSeconds(),
            self._bytesTotal,
            self._bytesLast / interval,
            self._packetsTotal,
            self._packetsLast / interval,
            ))

        self._bytesLast     = 0
        self._packetsLast   = 0

        ns.core.Simulator.Schedule(Seconds(interval), self.check_throughput)

    def process_flowmon(self, xml_filename):
        flowmon = self.flowmon_helper.GetMonitor()
        flowmon.CheckForLostPackets()
        flowmon.SerializeToXmlFile(xml_filename, True, True)


        return next(self._find_flow(dstAddr = self._server_sockaddr.GetIpv4(),
                                    dstPort = self._server_sockaddr.GetPort()))


    def _find_flow(self, srcAddr=None, srcPort=None, dstAddr=None, dstPort=None):
        flowmon = self.flowmon_helper.GetMonitor()
        classifier = self.flowmon_helper.GetClassifier()

        for flow_id, flow_stats in flowmon.GetFlowStats():
            flow = classifier.FindFlow(flow_id)

            def match(key, target):
                if key is None:
                    return True
                return key == target

            if (match(srcAddr, flow.sourceAddress) and
                match(srcPort, flow.sourcePort) and
                match(dstAddr, flow.destinationAddress) and
                match(dstPort, flow.destinationPort)):
                yield Flow(flow_id, flow, flow_stats)


class Flow(object):
    def __init__(self, flowid, flow, stats):
        self.id = flowid
        self.flow = flow
        self.stats = stats

    def __str__(self):
        proto = {6: 'TCP', 17: 'UDP'}[self.flow.protocol]
        return "FlowID: {}  ({} {}/{} --> {}/{})".format(
            self.id, proto,
            self.flow.sourceAddress, self.flow.sourcePort,
            self.flow.destinationAddress, self.flow.destinationPort)

    def print_stats(self):
        print(self)
        st = self.stats
        print("  First Tx Time:     {} ms".format(st.timeFirstTxPacket.GetSeconds() * 1000))
        print("  First Rx Time:     {} ms".format(st.timeFirstRxPacket.GetSeconds() * 1000))
        print("  Tx Bytes:          {}".format(st.txBytes))
        print("  Rx Bytes:          {}".format(st.rxBytes))
        print("  Tx Packets:        {}".format(st.txPackets))
        print("  Rx Packets:        {}".format(st.rxPackets))
        print("  Lost Packets:      {}".format(st.lostPackets))
        if st.rxPackets > 0:
            print("  Mean Delay:        {}".format(st.delaySum.GetSeconds() / st.rxPackets))
            print("  Mean Jitter:       {}".format(st.jitterSum.GetSeconds() / (st.rxPackets - 1)))
            print("  Mean Hop Count:    {}".format(float(st.timesForwarded) / (st.rxPackets + 1)))



def Distance3D(v1, v2):
    def squared(x):
        return math.pow(x, 2)

    return math.sqrt(
        squared(v2.x - v1.x) +
        squared(v2.y - v1.y) +
        squared(v2.z - v1.z))

def GetPosition(node):
    mob = node.GetObject(ns.mobility.MobilityModel.GetTypeId())
    return mob.GetPosition()

def FormatNode(node):
    ip4 = node.GetObject(ns.internet.Ipv4.GetTypeId())
    ipaddr = ip4.GetAddress(1,0).GetLocal()

    macaddr = node.GetDevice(0).GetAddress()

    return '{:<3} {:<12} {} {}'.format(
            node.GetId(), ipaddr, macaddr, GetPosition(node))


def ShowAllNodes(nodes):
    for node in (nodes.Get(i) for i in xrange(nodes.GetN())):
        print(FormatNode(node))


def SetupAodv(enable_hello):
    aodv = ns.aodv.AodvHelper()
    aodv.Set("EnableHello", BooleanValue(enable_hello))
    return aodv

protocol_map = {
    'AODV':     lambda: SetupAodv(True),
    'AODV-NH':  lambda: SetupAodv(False),
    'OLSR':     ns.olsr.OlsrHelper,
    'DSDV':     ns.dsdv.DsdvHelper,
}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', '--num-nodes', type=int, default=20,
            help='Number of nodes (default: %(default)d)')
    ap.add_argument('--placement', default='grid', choices=('grid', 'straight-line'),
            help='Controls the placement of nodes')
    ap.add_argument('--spacing', type=float, default=100.0,
            help='Controls the spacing of nodes (in meters)')
    ap.add_argument('-p', '--protocol', default='OLSR', choices=protocol_map.keys(),
            help='Routing protocol (default: %(default)s)')
    ap.add_argument('-l', '--log', dest='loglevel',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            default='WARNING',
            help='Set the logging level (default: %(default)s)')
    ap.add_argument('--visual', action='store_true',
            help='Enable visual simulator')

    return ap.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=args.loglevel)

    if args.visual:
        ns.core.GlobalValue.Bind('SimulatorImplementationType',
                StringValue("ns3::VisualSimulatorImpl"))


    sim = ManetSimulator(
            num_nodes = args.num_nodes,
            node_spacing = args.spacing,
            node_placement = args.placement,
            protocol = args.protocol,
            )

    ShowAllNodes(sim.nodes)

    print("Origin node:      {}".format(FormatNode(sim.origin)))
    print("Destination node: {}".format(FormatNode(sim.destination)))
    print("Distance:         {}".format(
        Distance3D(GetPosition(sim.origin), GetPosition(sim.destination)))
        )


    sim.check_throughput()

    # Run simulation
    ns.core.Simulator.Stop(Seconds(TOTAL_TIME))
    ns.core.Simulator.Run()

    flow = sim.process_flowmon("flowmon.xml")
    flow.print_stats()

    ns.core.Simulator.Destroy()

if __name__ == '__main__':
    main()
