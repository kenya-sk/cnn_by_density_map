#!/bin/sh -ex

SECONDS=0
python detector/train.py

echo "Computation Time: $((${SECONDS}/3600))hour $((${SECONDS}%3600/60))minute $((${SECONDS}%60))second"