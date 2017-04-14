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
#
import argparse

import ns.applications
import ns.core
from ns.core import DoubleValue, StringValue, UintegerValue
import ns.internet
import ns.network
import ns.wifi

import readline
import rlcompleter

def setup_wifi_phy():
    chanhlp = ns.wifi.YansWifiChannelHelper()
    chanhlp.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel")
    chanhlp.AddPropagationLoss("ns3::FriisPropagationLossModel")

    phy = ns.wifi.YansWifiPhyHelper.Default()
    phy.SetChannel(chanhlp.Create())

    txp = DoubleValue(7.5)
    phy.Set("TxPowerStart", txp)
    phy.Set("TxPowerEnd", txp)

    return phy

def setup_wifi_mac():
    """Set up non-QoS MAC"""
    mac = ns.wifi.NqosWifiMacHelper.Default()
    mac.SetType("ns3::AdhocWifiMac")
    return mac



def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', '--num-nodes', type=int, default=20,
            help='Number of nodes (default: %(default)d)')

    return ap.parse_args()

def main():
    args = parse_args()

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



    #readline.parse_and_bind('tab: complete')
    #import code; code.interact(local=locals())

if __name__ == '__main__':
    main()
