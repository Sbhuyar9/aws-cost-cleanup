"""Find unattached (status=available) EBS volumes: storage you pay for that no
instance is using. Reports by default; deletes only with --execute.

Safety rules:
  * volumes tagged Keep=true are never reported as deletable
  * --min-age-days avoids flagging volumes that were just detached
  * deletion requires --execute (default is report-only)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys

from .common import age_days, get_client, has_keep_tag, list_regions, name_of, setup_logging

log = logging.getLogger("ebs_volumes")

# Approximate USD per GB-month (us-east-1 list prices). Estimates only:
# prices vary by region, so treat the output as a rough guide.
PRICE_PER_GB_MONTH = {
    "gp3": 0.08, "gp2": 0.10, "io1": 0.125, "io2": 0.125,
    "st1": 0.045, "sc1": 0.015, "standard": 0.05,
}


def monthly_cost(volume_type: str, size_gb: int) -> float:
    return round(PRICE_PER_GB_MONTH.get(volume_type, 0.10) * size_gb, 2)


def find_unattached(ec2, min_age_days: float = 0, region: str | None = None) -> list[dict]:
    rows: list[dict] = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate(Filters=[{"Name": "status", "Values": ["available"]}]):
        for v in page["Volumes"]:
            age = age_days(v["CreateTime"])
            if age < min_age_days:
                continue
            rows.append({
                "region": region or "",
                "volume_id": v["VolumeId"],
                "name": name_of(v.get("Tags")),
                "size_gb": v["Size"],
                "type": v["VolumeType"],
                "age_days": int(age),
                "est_monthly_usd": monthly_cost(v["VolumeType"], v["Size"]),
                "protected": has_keep_tag(v.get("Tags")),
            })
    return rows


def delete_volumes(ec2, rows: list[dict], execute: bool) -> int:
    deleted = 0
    for r in rows:
        if r["protected"]:
            log.info("skip %s (Keep=true)", r["volume_id"])
            continue
        if not execute:
            log.info("[dry-run] would delete %s (%s GB, ~$%.2f/mo)",
                     r["volume_id"], r["size_gb"], r["est_monthly_usd"])
            continue
        ec2.delete_volume(VolumeId=r["volume_id"])
        log.info("deleted %s", r["volume_id"])
        deleted += 1
    return deleted


def render(rows: list[dict], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(rows, indent=2)
    if fmt == "csv":
        import io
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return buf.getvalue()
    if not rows:
        return "No unattached volumes found."
    header = f"{'REGION':<14}{'VOLUME':<24}{'GB':>6} {'TYPE':<6}{'AGE(d)':>7}{'$/MO':>9}  NAME"
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(f"{r['region']:<14}{r['volume_id']:<24}{r['size_gb']:>6} {r['type']:<6}"
                     f"{r['age_days']:>7}{r['est_monthly_usd']:>9.2f}  {r['name']}"
                     f"{' [KEEP]' if r['protected'] else ''}")
    total = sum(r["est_monthly_usd"] for r in rows if not r["protected"])
    lines.append(f"\n{len(rows)} volume(s); estimated waste: ${total:.2f}/month")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Find (and optionally delete) unattached EBS volumes.")
    p.add_argument("--region", action="append")
    p.add_argument("--all-regions", action="store_true")
    p.add_argument("--profile")
    p.add_argument("--min-age-days", type=float, default=7,
                   help="Ignore volumes younger than this (default: 7).")
    p.add_argument("--format", choices=["table", "json", "csv"], default="table")
    p.add_argument("--execute", action="store_true",
                   help="Actually delete the volumes. Without it, report only.")
    p.add_argument("--delete", action="store_true", help="Enable deletion mode (needs --execute to act).")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    regions = list_regions(args.profile) if args.all_regions else (args.region or [None])
    all_rows: list[dict] = []
    failures = 0
    for region in regions:
        try:
            ec2 = get_client("ec2", region=region, profile=args.profile)
            rows = find_unattached(ec2, args.min_age_days, region)
            all_rows.extend(rows)
            if args.delete:
                delete_volumes(ec2, rows, args.execute)
        except Exception:
            log.exception("failed in region %s", region)
            failures += 1
    print(render(all_rows, args.format))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
