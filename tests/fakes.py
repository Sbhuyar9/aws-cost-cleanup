"""Tiny fake EC2 client so tests need neither boto3 nor AWS credentials."""


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        return iter(self.pages)


class FakeEC2:
    def __init__(self, instances=None, volumes=None, snapshots=None, images=None):
        self.data = {
            "describe_instances": [{"Reservations": [{"Instances": instances or []}]}],
            "describe_volumes": [{"Volumes": volumes or []}],
            "describe_snapshots": [{"Snapshots": snapshots or []}],
            "describe_images": [{"Images": images or []}],
        }
        self.calls = []

    def get_paginator(self, name):
        return FakePaginator(self.data[name])

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))

    def start_instances(self, **kw): self._record("start_instances", **kw)
    def stop_instances(self, **kw): self._record("stop_instances", **kw)
    def delete_volume(self, **kw): self._record("delete_volume", **kw)
    def delete_snapshot(self, **kw): self._record("delete_snapshot", **kw)
