#!/usr/bin/env bash
# Weekly housekeeping: report unattached EBS volumes, then prune old snapshots.
# Dry-run by default. Set EXECUTE=1 to really delete snapshots:
#   EXECUTE=1 ./weekly_cleanup.sh --region ap-south-1
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
acquire_lock

REPORT_DIR="$REPO_DIR/reports"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%d)"

log "unattached EBS volume report"
python3 -m aws_cleanup.ebs_volumes --format csv "$@" > "$REPORT_DIR/unattached_volumes_$STAMP.csv"
python3 -m aws_cleanup.ebs_volumes "$@" | tee -a "$LOG_DIR/ebs_volumes.log"

log "EBS snapshot cleanup (execute=${EXECUTE:-0})"
EXTRA=()
[[ "${EXECUTE:-0}" == "1" ]] && EXTRA+=(--execute)
python3 -m aws_cleanup.ebs_snapshots "${EXTRA[@]}" "$@" 2>&1 | tee -a "$LOG_DIR/ebs_snapshots.log"
