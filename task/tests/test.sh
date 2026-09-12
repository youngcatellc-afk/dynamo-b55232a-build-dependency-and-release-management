#!/bin/bash
#
# Runs inside the shared environment image. pytest and its CTRF plugin are baked into
# that image at build time, so nothing is installed here. This script always exits 0;
# the verdict is the 1 or 0 that score.py writes to /logs/verifier/reward.txt.
#
# The run is pinned to /tests - working directory, rootdir and conftest cut-off all sit
# there - so nothing the agent leaves under /app can be picked up as configuration or as
# a plugin. score.py then reads the verdict out of the CTRF report rather than off the
# exit status, and awards a one only when every expected check ran and passed.
mkdir -p /logs/verifier
rm -f /logs/verifier/ctrf.json

cd /tests || exit 0

pytest --rootdir=/tests --confcutdir=/tests -p no:cacheprovider \
    --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
PYTEST_STATUS=$? python3 /tests/score.py

exit 0
