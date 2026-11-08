# AWS Cost Cleanup Scripts

Python (boto3) and Bash automation for routine AWS housekeeping that cuts idle cloud spend.

| Script | What it does |
|---|---|
| `ec2_scheduler.py` | Starts/stops tagged dev EC2 instances on a schedule so they are not billed when unused |
| `ebs_volumes.py` | Finds unattached (`available`) EBS volumes, estimates their monthly cost, optionally deletes them |
| `ebs_snapshots.py` | Deletes old EBS snapshots past a retention window |
| `scripts/*.sh` | Bash wrappers for unattended runs: venv, logging, lock file, cron-friendly |

## Safety model

Cleanup tools should be hard to misuse, so the defaults are conservative:

- **Tag-based opt-in for EC2.** Only instances tagged `Environment=dev` **and** `Schedule=office-hours` are touched (both configurable).
- **`Keep=true` protects any resource** (instance, volume, snapshot) from every script.
- **Destructive actions are dry-run by default.** Volumes and snapshots are deleted only with `--execute` (volumes also need `--delete`).
- **Snapshots backing an AMI are skipped**, and `--keep-latest N` (default 1) always preserves the newest snapshots of each volume.
- **`--min-age-days`** stops freshly detached volumes from being flagged.
- **Least-privilege IAM** policy in `iam/policy.json`; start/stop is limited to `Environment=dev` instances.

## Setup

```bash
git clone <your-repo-url> aws-cost-cleanup && cd aws-cost-cleanup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
aws configure --profile cost-cleanup      # or use an instance role / SSO
export AWS_PROFILE=cost-cleanup AWS_REGION=ap-south-1
```

Tag the instances you want scheduled:

```bash
aws ec2 create-tags --resources i-0123456789abcdef0 \
  --tags Key=Environment,Value=dev Key=Schedule,Value=office-hours
```

## Usage

```bash
# EC2 start/stop (add --dry-run to preview; --all-regions to sweep every region)
python -m aws_cleanup.ec2_scheduler stop  --dry-run
python -m aws_cleanup.ec2_scheduler start --region ap-south-1

# Unattached EBS volumes: report (table | json | csv)
python -m aws_cleanup.ebs_volumes --all-regions --min-age-days 7
python -m aws_cleanup.ebs_volumes --format csv > unattached.csv
# ...and delete them (only after reviewing the report)
python -m aws_cleanup.ebs_volumes --delete --execute

# Old snapshots: dry-run first, then --execute
python -m aws_cleanup.ebs_snapshots --retention-days 30 --keep-latest 1
python -m aws_cleanup.ebs_snapshots --retention-days 30 --execute
```

Sample volume report:

```
REGION        VOLUME                    GB TYPE    AGE(d)     $/MO  NAME
------------------------------------------------------------------------
ap-south-1    vol-0abc123def4567890    200 gp3         45    16.00  old-etl-data
ap-south-1    vol-0123456789abcdef0     50 gp2         12     5.00

2 volume(s); estimated waste: $21.00/month
```

## Running unattended

Use the Bash wrappers with cron (see `cron/crontab.example`):

```cron
30 8  * * 1-5  /opt/aws-cost-cleanup/scripts/start_dev.sh
0  20 * * 1-5  /opt/aws-cost-cleanup/scripts/stop_dev.sh
0  2  * * 0     EXECUTE=1 /opt/aws-cost-cleanup/scripts/weekly_cleanup.sh
```

The wrappers use strict mode (`set -euo pipefail`), activate `.venv`, append to `logs/`, and take a `flock`
lock so overlapping runs exit cleanly. `weekly_cleanup.sh` also writes a dated CSV to `reports/`.

Prefer serverless? The same modules work in Lambda: call `ec2_scheduler.run(...)` from a handler
triggered by EventBridge Scheduler rules.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest        # or: python -m unittest discover
```

Tests use a small fake EC2 client, so they run offline without AWS credentials.

## Project layout

```
aws_cleanup/
  common.py          logging, boto3 client factory, tag/age helpers
  ec2_scheduler.py   start/stop tagged dev instances
  ebs_volumes.py     unattached volume finder + optional delete
  ebs_snapshots.py   old snapshot cleanup
scripts/             Bash wrappers (start_dev, stop_dev, weekly_cleanup)
cron/crontab.example schedule examples
iam/policy.json      least-privilege IAM policy
tests/               unit tests
```

## Notes and limits

- Cost figures are rough us-east-1 list-price estimates for prioritising cleanup, not billing data.
  Snapshots are incremental, so real savings from deleting one are usually lower than its size suggests.
- Stopped instances still incur EBS storage charges; scheduling saves compute cost only.
- Always run with `--dry-run` / without `--execute` in a new account first.
