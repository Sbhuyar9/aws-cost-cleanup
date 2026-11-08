import unittest
from datetime import datetime, timedelta, timezone

from aws_cleanup import ebs_snapshots as snaps
from aws_cleanup import ebs_volumes as vols
from tests.fakes import FakeEC2

NOW = datetime.now(timezone.utc)


def vol(vid, days_old, size=100, vtype="gp3", tags=None):
    return {"VolumeId": vid, "CreateTime": NOW - timedelta(days=days_old), "Size": size,
            "VolumeType": vtype, "Tags": tags or []}


def snap(sid, days_old, volume="vol-a", size=50, tags=None):
    return {"SnapshotId": sid, "VolumeId": volume, "VolumeSize": size,
            "StartTime": NOW - timedelta(days=days_old), "Tags": tags or []}


class VolumeTests(unittest.TestCase):
    def test_min_age_filters_recent_volumes(self):
        ec2 = FakeEC2(volumes=[vol("vol-old", 30), vol("vol-new", 1)])
        rows = vols.find_unattached(ec2, min_age_days=7)
        self.assertEqual([r["volume_id"] for r in rows], ["vol-old"])

    def test_cost_estimate(self):
        self.assertEqual(vols.monthly_cost("gp3", 100), 8.0)

    def test_report_only_deletes_nothing(self):
        ec2 = FakeEC2(volumes=[vol("vol-1", 30)])
        rows = vols.find_unattached(ec2)
        vols.delete_volumes(ec2, rows, execute=False)
        self.assertEqual(ec2.calls, [])

    def test_execute_deletes_but_skips_keep(self):
        keep = [{"Key": "Keep", "Value": "true"}]
        ec2 = FakeEC2(volumes=[vol("vol-1", 30), vol("vol-2", 30, tags=keep)])
        rows = vols.find_unattached(ec2)
        n = vols.delete_volumes(ec2, rows, execute=True)
        self.assertEqual(n, 1)
        self.assertEqual(ec2.calls, [("delete_volume", {"VolumeId": "vol-1"})])

    def test_render_formats(self):
        rows = vols.find_unattached(FakeEC2(volumes=[vol("vol-1", 30)]))
        self.assertIn("vol-1", vols.render(rows, "table"))
        self.assertIn("volume_id", vols.render(rows, "csv"))
        self.assertIn('"vol-1"', vols.render(rows, "json"))


class SnapshotTests(unittest.TestCase):
    def test_retention_window(self):
        ec2 = FakeEC2(snapshots=[snap("snap-old", 90), snap("snap-new", 5)])
        expired = snaps.find_expired(ec2, retention_days=30)
        self.assertEqual([s["snapshot_id"] for s in expired], ["snap-old"])

    def test_ami_backed_snapshot_is_skipped(self):
        images = [{"BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-ami"}}]}]
        ec2 = FakeEC2(snapshots=[snap("snap-ami", 90), snap("snap-x", 90)], images=images)
        expired = snaps.find_expired(ec2, retention_days=30)
        self.assertEqual([s["snapshot_id"] for s in expired], ["snap-x"])

    def test_keep_tag_is_skipped(self):
        keep = [{"Key": "Keep", "Value": "true"}]
        ec2 = FakeEC2(snapshots=[snap("snap-k", 90, tags=keep)])
        self.assertEqual(snaps.find_expired(ec2, retention_days=30), [])

    def test_keep_latest_per_volume(self):
        ec2 = FakeEC2(snapshots=[snap("s1", 100), snap("s2", 60), snap("s3", 40)])
        expired = snaps.find_expired(ec2, retention_days=30, keep_latest=1)
        self.assertEqual({s["snapshot_id"] for s in expired}, {"s1", "s2"})

    def test_dry_run_vs_execute(self):
        ec2 = FakeEC2(snapshots=[snap("s1", 90)])
        expired = snaps.find_expired(ec2, retention_days=30)
        snaps.delete_snapshots(ec2, expired, execute=False)
        self.assertEqual(ec2.calls, [])
        snaps.delete_snapshots(ec2, expired, execute=True)
        self.assertEqual(ec2.calls, [("delete_snapshot", {"SnapshotId": "s1"})])


if __name__ == "__main__":
    unittest.main()
