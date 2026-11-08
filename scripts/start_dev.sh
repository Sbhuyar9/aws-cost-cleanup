#!/usr/bin/env bash
# Start scheduled dev EC2 instances (run each weekday morning).
# Extra args are passed through, e.g.: ./start_dev.sh --region ap-south-1 --dry-run
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
acquire_lock
log "starting dev instances"
python3 -m aws_cleanup.ec2_scheduler start "$@" 2>&1 | tee -a "$LOG_DIR/ec2_scheduler.log"
