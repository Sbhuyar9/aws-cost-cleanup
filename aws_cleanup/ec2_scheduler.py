"""Start/stop dev EC2 instances so they are not billed when nobody uses them.

Instances are selected by tags, never by name or ID, so the script is safe
to run in shared accounts:

    Environment=dev        (configurable)
    Schedule=office-hours  (configurable; opt-in marker)

Instances tagged Keep=true are never touched.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .common import get_client, has_keep_tag, list_regions, name_of, setup_logging

log = logging.getLogger("ec2_scheduler")

# Action -> instance states we are allowed to act on, and the boto3 call.
ACTIONS = {
    "start": {"from_states": ["stopped"], "api": "start_instances"},
    "stop": {"from_states": ["running"], "api": "stop_instances"},
}


def find_instances(ec2, action: str, env_tag: str, env_value: str,
                   schedule_tag: str, schedule_value: str) -> list[dict]:
    """Return instances eligible for `action`."""
    filters = [
        {"Name": f"tag:{env_tag}", "Values": [env_value]},
        {"Name": f"tag:{schedule_tag}", "Values": [schedule_value]},
        {"Name": "instance-state-name", "Values": ACTIONS[action]["from_states"]},
    ]
    found: list[dict] = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=filters):
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                if has_keep_tag(inst.get("Tags")):
                    log.info("skip %s (Keep=true)", inst["InstanceId"])
                    continue
                found.append(inst)
    return found


def apply_action(ec2, action: str, instances: list[dict], dry_run: bool) -> list[str]:
    ids = [i["InstanceId"] for i in instances]
    if not ids:
        return []
    for inst in instances:
        log.info("%s%s %s (%s, %s)", "[dry-run] " if dry_run else "", action,
                 inst["InstanceId"], inst.get("InstanceType", "?"),
                 name_of(inst.get("Tags")) or "-")
    if dry_run:
        return ids
    getattr(ec2, ACTIONS[action]["api"])(InstanceIds=ids)
    return ids


def run(action: str, region: str | None, profile: str | None, env_tag: str, env_value: str,
        schedule_tag: str, schedule_value: str, dry_run: bool, ec2=None) -> list[str]:
    ec2 = ec2 or get_client("ec2", region=region, profile=profile)
    instances = find_instances(ec2, action, env_tag, env_value, schedule_tag, schedule_value)
    log.info("%s: %d instance(s) eligible to %s", region or "default region", len(instances), action)
    return apply_action(ec2, action, instances, dry_run)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Start or stop scheduled dev EC2 instances.")
    p.add_argument("action", choices=sorted(ACTIONS))
    p.add_argument("--region", action="append", help="Region (repeatable). Default: AWS_REGION env.")
    p.add_argument("--all-regions", action="store_true", help="Run in every enabled region.")
    p.add_argument("--profile", help="AWS profile name.")
    p.add_argument("--env-tag", default="Environment")
    p.add_argument("--env-value", default="dev")
    p.add_argument("--schedule-tag", default="Schedule")
    p.add_argument("--schedule-value", default="office-hours")
    p.add_argument("--dry-run", action="store_true", help="Log what would happen, change nothing.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    regions = list_regions(args.profile) if args.all_regions else (args.region or [None])
    failures = 0
    for region in regions:
        try:
            run(args.action, region, args.profile, args.env_tag, args.env_value,
                args.schedule_tag, args.schedule_value, args.dry_run)
        except Exception:  # keep going so one bad region doesn't block the rest
            log.exception("failed in region %s", region)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
