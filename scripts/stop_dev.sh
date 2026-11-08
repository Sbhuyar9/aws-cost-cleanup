#!/usr/bin/env bash
# Stop scheduled dev EC2 instances (run each weekday evening).
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
acquire_lock
log "stopping dev instances"
python3 -m aws_cleanup.ec2_scheduler stop "$@" 2>&1 | tee -a "$LOG_DIR/ec2_scheduler.log"
