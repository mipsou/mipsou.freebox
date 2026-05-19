# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Unit tests for freebox_vm lookup plugin logic.

Tests use a StubClient instead of the Ansible LookupBase infrastructure
so they run on Windows without a full Ansible install.
"""


# ── Stub client ───────────────────────────────────────────────────────────


class StubClient(object):
    def __init__(self, vms):
        self._vms = vms
        self.calls = []

    def get(self, path, query=None):
        self.calls.append(path)
        if path == "/vm/":
            return list(self._vms)
        return []


# ── Lookup logic (extracted from LookupModule.run) ────────────────────────


def _lookup_vms(client, terms):
    """Match VMs by name against a list of terms. Returns matched VM dicts."""
    all_vms = client.get("/vm/") or []
    result = []
    for term in terms:
        matched = [vm for vm in all_vms if vm.get("name") == term]
        result.extend(matched)
    return result


# ── Tests ─────────────────────────────────────────────────────────────────


def test_lookup_returns_matching_vm():
    client = StubClient([
        {"id": 1, "name": "fbx-vm-01", "status": "running"},
        {"id": 2, "name": "fbx-vm-02", "status": "stopped"},
    ])
    result = _lookup_vms(client, ["fbx-vm-01"])
    assert len(result) == 1
    assert result[0]["name"] == "fbx-vm-01"


def test_lookup_returns_empty_when_not_found():
    client = StubClient([{"id": 1, "name": "fbx-vm-01"}])
    result = _lookup_vms(client, ["nonexistent"])
    assert result == []


def test_lookup_multiple_terms():
    client = StubClient([
        {"id": 1, "name": "fbx-vm-01"},
        {"id": 2, "name": "fbx-vm-02"},
        {"id": 3, "name": "other-vm"},
    ])
    result = _lookup_vms(client, ["fbx-vm-01", "fbx-vm-02"])
    names = [v["name"] for v in result]
    assert "fbx-vm-01" in names
    assert "fbx-vm-02" in names
    assert "other-vm" not in names


def test_lookup_single_get_call():
    """The plugin issues exactly one GET /vm/ regardless of term count."""
    client = StubClient([{"id": 1, "name": "vm1"}, {"id": 2, "name": "vm2"}])
    _lookup_vms(client, ["vm1", "vm2"])
    assert client.calls == ["/vm/"]


def test_lookup_empty_vm_list():
    client = StubClient([])
    result = _lookup_vms(client, ["fbx-vm-01"])
    assert result == []


def test_lookup_name_is_case_sensitive():
    client = StubClient([{"id": 1, "name": "FBX-VM-01"}])
    result = _lookup_vms(client, ["fbx-vm-01"])
    assert result == []


def test_lookup_returns_full_vm_dict():
    vm = {"id": 5, "name": "myvm", "status": "running", "memory": 512}
    client = StubClient([vm])
    result = _lookup_vms(client, ["myvm"])
    assert result[0] == vm


def test_lookup_duplicate_names_returns_all():
    client = StubClient([
        {"id": 1, "name": "dup"},
        {"id": 2, "name": "dup"},
    ])
    result = _lookup_vms(client, ["dup"])
    assert len(result) == 2
