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
from ns.core import DoubleValue, StringValue, UintegerValue
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

def setup_wifi_phy():
    chanhlp = ns.wifi.YansWifiChannelHelper()
    chanhlp.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel")
    chanhlp.AddPropagationLoss("ns3::FriisPropagationLossModel")

    phy = ns.wifi.YansWifiPhyHelper.Default()
    phy.SetChannel(chanhlp.Create())

    txp = DoubleValue(WIFI_TX_POWER)
    phy.Set("TxPowerStart", txp)
    phy.Set("TxPowerEnd", txp)

    return phy

def setup_wifi_mac():
    """Set up non-QoS MAC"""
    mac = ns.wifi.NqosWifiMacHelper.Default()
    mac.SetType("ns3::AdhocWifiMac")
    return mac

def setup_mobility():
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

def setup_routing(args):
    protocol = protocol_map[args.protocol]()
    route_list = ns.internet.Ipv4ListRoutingHelper()
    route_list.Add(protocol, 100)

    inet = ns.internet.InternetStackHelper()
    inet.SetRoutingHelper(route_list)
    return inet

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


    # Create a container with the desired number of nodes
    adhocNodes = ns.network.NodeContainer();
    adhocNodes.Create(args.num_nodes)

    # Set up Wifi devices
    phyMode = StringValue("DsssRate11Mbps")

    wifi = ns.wifi.WifiHelper()
    wifi.SetStandard(ns.wifi.WIFI_PHY_STANDARD_80211b)
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode", phyMode,
                                 "ControlMode", phyMode)

    wifiPhy = setup_wifi_phy()
    wifiMac = setup_wifi_mac()
    adhocDevices = wifi.Install(wifiPhy, wifiMac, adhocNodes)

    # Set up mobility
    mobility = setup_mobility()
    mobility.Install(adhocNodes)

    # Set up routing
    inet = setup_routing(args)
    inet.Install(adhocNodes)


    #readline.parse_and_bind('tab: complete')
    #import code; code.interact(local=locals())

if __name__ == '__main__':
    main()
