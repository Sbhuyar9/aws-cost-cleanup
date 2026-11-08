"""Shared helpers: logging, boto3 client creation, tag and age utilities."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Iterable

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=LOG_FORMAT,
        stream=sys.stdout,
    )
    # boto3 is chatty at DEBUG; keep it quiet unless explicitly asked.
    for noisy in ("boto3", "botocore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_client(service: str, region: str | None = None, profile: str | None = None):
    """Create a boto3 client. boto3 is imported lazily so unit tests can run
    with fake clients and without AWS credentials."""
    import boto3

    session = boto3.Session(
        profile_name=profile or os.environ.get("AWS_PROFILE"),
        region_name=region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
    )
    return session.client(service)


def list_regions(profile: str | None = None, region: str | None = None) -> list[str]:
    """All regions enabled for the account."""
    ec2 = get_client("ec2", region=region or "us-east-1", profile=profile)
    resp = ec2.describe_regions(AllRegions=False)
    return sorted(r["RegionName"] for r in resp["Regions"])


def tags_to_dict(tags: Iterable[dict] | None) -> dict[str, str]:
    return {t["Key"]: t["Value"] for t in (tags or [])}


def has_keep_tag(tags: Iterable[dict] | None, key: str = "Keep") -> bool:
    """True if the resource is protected with Keep=true (case-insensitive)."""
    return tags_to_dict(tags).get(key, "").strip().lower() in {"true", "yes", "1"}


def age_days(created: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created).total_seconds() / 86400


def name_of(tags: Iterable[dict] | None) -> str:
    return tags_to_dict(tags).get("Name", "")
