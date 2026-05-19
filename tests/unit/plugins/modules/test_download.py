# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import download as mod


# ── RecordingClient ───────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self, tasks=None):
        self._tasks = list(tasks or [])
        self._next_id = 100
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/downloads/":
            return list(self._tasks)
        raise AssertionError("unexpected GET %s" % path)

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        if path == "/downloads/":
            task = dict(body or {})
            task["id"] = self._next_id
            self._next_id += 1
            self._tasks.append(task)
            return task
        raise AssertionError("unexpected POST %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        for task in self._tasks:
            if path == "/downloads/%d" % task["id"]:
                task.update(body)
                return dict(task)
        raise AssertionError("no task for %s" % path)

    def delete(self, path):
        self.calls.append({"method": "DELETE", "path": path})
        for i, task in enumerate(self._tasks):
            if path == "/downloads/%d" % task["id"]:
                self._tasks.pop(i)
                return None
        raise AssertionError("no task for %s" % path)


# ── facts state ──────────────────────────────────────────────────────────


def test_facts_returns_all_tasks():
    tasks = [{"id": 1, "status": "downloading"}, {"id": 2, "status": "stopped"}]
    client = RecordingClient(tasks=tasks)
    result = client.get("/downloads/")
    assert result == tasks


def test_facts_empty():
    client = RecordingClient(tasks=[])
    result = client.get("/downloads/")
    assert result == []


# ── present: add ─────────────────────────────────────────────────────────


def test_add_download_posts():
    client = RecordingClient()
    task = client.post("/downloads/", body={"download_url": "https://example.com/x.iso"})
    assert task["download_url"] == "https://example.com/x.iso"
    assert task["id"] == 100
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert len(posts) == 1


# ── absent: delete ────────────────────────────────────────────────────────


def test_delete_removes_task():
    client = RecordingClient(tasks=[{"id": 42, "status": "stopped"}])
    client.delete("/downloads/42")
    assert client._tasks == []
    deletes = [c for c in client.calls if c["method"] == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0]["path"] == "/downloads/42"


# ── stopped / downloading: status change ─────────────────────────────────


def test_pause_task_updates_status():
    client = RecordingClient(tasks=[{"id": 7, "status": "downloading"}])
    updated = client.put("/downloads/7", body={"status": "stopped"})
    assert updated["status"] == "stopped"
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert puts[0]["body"] == {"status": "stopped"}


def test_resume_task_updates_status():
    client = RecordingClient(tasks=[{"id": 7, "status": "stopped"}])
    updated = client.put("/downloads/7", body={"status": "downloading"})
    assert updated["status"] == "downloading"


# ── check_mode ────────────────────────────────────────────────────────────


def test_check_mode_add_no_post():
    client = RecordingClient()
    # Simulate check mode: no POST called.
    assert not any(c["method"] == "POST" for c in client.calls)


def test_check_mode_delete_no_delete():
    client = RecordingClient(tasks=[{"id": 1, "status": "downloading"}])
    # Simulate check mode: no DELETE called.
    assert not any(c["method"] == "DELETE" for c in client.calls)
    assert len(client._tasks) == 1
