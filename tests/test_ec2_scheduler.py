import unittest

from aws_cleanup import ec2_scheduler as sched
from tests.fakes import FakeEC2


def inst(iid, tags=None):
    return {"InstanceId": iid, "InstanceType": "t3.micro", "Tags": tags or []}


class SchedulerTests(unittest.TestCase):
    def run_action(self, action, ec2, dry_run=False):
        return sched.run(action, "ap-south-1", None, "Environment", "dev",
                         "Schedule", "office-hours", dry_run, ec2=ec2)

    def test_stop_calls_api_with_ids(self):
        ec2 = FakeEC2(instances=[inst("i-1"), inst("i-2")])
        ids = self.run_action("stop", ec2)
        self.assertEqual(ids, ["i-1", "i-2"])
        self.assertEqual(ec2.calls, [("stop_instances", {"InstanceIds": ["i-1", "i-2"]})])

    def test_start_calls_start_api(self):
        ec2 = FakeEC2(instances=[inst("i-1")])
        self.run_action("start", ec2)
        self.assertEqual(ec2.calls[0][0], "start_instances")

    def test_dry_run_makes_no_changes(self):
        ec2 = FakeEC2(instances=[inst("i-1")])
        ids = self.run_action("stop", ec2, dry_run=True)
        self.assertEqual(ids, ["i-1"])
        self.assertEqual(ec2.calls, [])

    def test_keep_tag_is_respected(self):
        ec2 = FakeEC2(instances=[inst("i-1", [{"Key": "Keep", "Value": "true"}]), inst("i-2")])
        ids = self.run_action("stop", ec2)
        self.assertEqual(ids, ["i-2"])

    def test_nothing_eligible_makes_no_call(self):
        ec2 = FakeEC2(instances=[])
        self.assertEqual(self.run_action("stop", ec2), [])
        self.assertEqual(ec2.calls, [])


if __name__ == "__main__":
    unittest.main()
