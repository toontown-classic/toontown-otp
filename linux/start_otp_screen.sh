#!/bin/sh
cd ..
screen python -m realtime.main --no-clientagent --no-stateserver --no-database
screen python -m realtime.main --no-messagedirector
