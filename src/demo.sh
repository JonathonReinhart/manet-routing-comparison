#!/bin/bash
rm -f *.pcap
./jrr_manet_sim.py \
    -p AODV-NH \
    --visual \
    --num-nodes 4 \
    --placement straight-line \
    --spacing 150
