"""Delete old EBS snapshots so snapshot storage does not grow unchecked.

Safety rules:
  * only snapshots owned by this account are considered
  * snapshots older than --retention-days are candidates
  * snapshots backing a registered AMI are skipped (AWS refuses to delete them
    anyway, and deregistering AMIs is a separate decision)
  * snapshots tagged Keep=true are skipped
  * --keep-latest N always keeps the N newest snapshots of each volume
  * deletion requires --execute (default is dry-run)
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict

from .common import age_days, get_client, has_keep_tag, list_regions, setup_logging

log = logging.getLogger("ebs_snapshots")

# Approximate USD per GB-month for snapshot storage (upper bound: snapshots are
# incremental, so real cost is usually lower than size * price).
SNAPSHOT_PRICE_PER_GB_MONTH = 0.05


def ami_snapshot_ids(ec2) -> set[str]:
    ids: set[str] = set()
    paginator = ec2.get_paginator("describe_images")
    for page in paginator.paginate(Owners=["self"]):
        for image in page["Images"]:
            for bdm in image.get("BlockDeviceMappings", []):
                snap = bdm.get("Ebs", {}).get("SnapshotId")
                if snap:
                    ids.add(snap)
    return ids


def find_expired(ec2, retention_days: int, keep_latest: int = 0, now=None) -> list[dict]:
    protected_by_ami = ami_snapshot_ids(ec2)
    snapshots: list[dict] = []
    paginator = ec2.get_paginator("describe_snapshots")
    for page in paginator.paginate(OwnerIds=["self"]):
        snapshots.extend(page["Snapshots"])

    # Newest-first per source volume, so --keep-latest is easy to apply.
    by_volume: dict[str, list[dict]] = defaultdict(list)
    for s in snapshots:
        by_volume[s.get("VolumeId", "unknown")].append(s)
    protected_latest: set[str] = set()
    if keep_latest > 0:
        for snaps in by_volume.values():
            snaps.sort(key=lambda s: s["StartTime"], reverse=True)
            protected_latest.update(s["SnapshotId"] for s in snaps[:keep_latest])

    expired: list[dict] = []
    for s in snapshots:
        sid = s["SnapshotId"]
        age = age_days(s["StartTime"], now)
        if age < retention_days:
            continue
        if sid in protected_by_ami:
            log.info("skip %s (used by an AMI)", sid)
            continue
        if has_keep_tag(s.get("Tags")):
            log.info("skip %s (Keep=true)", sid)
            continue
        if sid in protected_latest:
            log.info("skip %s (within --keep-latest %d)", sid, keep_latest)
            continue
        expired.append({
            "snapshot_id": sid,
            "volume_id": s.get("VolumeId", ""),
            "size_gb": s["VolumeSize"],
            "age_days": int(age),
            "est_monthly_usd": round(s["VolumeSize"] * SNAPSHOT_PRICE_PER_GB_MONTH, 2),
        })
    return expired


def delete_snapshots(ec2, expired: list[dict], execute: bool) -> int:
    deleted = 0
    for s in expired:
        if not execute:
            log.info("[dry-run] would delete %s (%s GB, %d days old)",
                     s["snapshot_id"], s["size_gb"], s["age_days"])
            continue
        try:
            ec2.delete_snapshot(SnapshotId=s["snapshot_id"])
            log.info("deleted %s", s["snapshot_id"])
            deleted += 1
        except Exception as exc:  # e.g. snapshot in use; keep going
            log.warning("could not delete %s: %s", s["snapshot_id"], exc)
    return deleted


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Clean up old EBS snapshots.")
    p.add_argument("--region", action="append")
    p.add_argument("--all-regions", action="store_true")
    p.add_argument("--profile")
    p.add_argument("--retention-days", type=int, default=30)
    p.add_argument("--keep-latest", type=int, default=1,
                   help="Always keep the N newest snapshots per volume (default: 1).")
    p.add_argument("--execute", action="store_true", help="Actually delete. Default is dry-run.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    regions = list_regions(args.profile) if args.all_regions else (args.region or [None])
    failures = 0
    for region in regions:
        try:
            ec2 = get_client("ec2", region=region, profile=args.profile)
            expired = find_expired(ec2, args.retention_days, args.keep_latest)
            saved = sum(s["est_monthly_usd"] for s in expired)
            log.info("%s: %d expired snapshot(s), up to ~$%.2f/month",
                     region or "default region", len(expired), saved)
            delete_snapshots(ec2, expired, args.execute)
        except Exception:
            log.exception("failed in region %s", region)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
