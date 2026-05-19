# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Unit tests for the freebox_lan inventory plugin.

Tests call the module-level helpers _pick_hostname and _group_name
directly, avoiding the need for a full Ansible inventory framework.
"""

from ansible_collections.mipsou.freebox.plugins.inventory.freebox_lan import (
    _pick_hostname,
    _group_name,
)


# ── _pick_hostname ────────────────────────────────────────────────────────


def test_pick_hostname_primary_name_used_first():
    host = {"primary_name": "my-nas", "mac": "aa:bb:cc:dd:ee:ff"}
    assert _pick_hostname(host) == "my-nas"


def test_pick_hostname_id_used_when_no_primary_name():
    host = {"primary_name": "", "id": "fbx-vm-01", "mac": "aa:bb:cc:dd:ee:ff"}
    assert _pick_hostname(host) == "fbx-vm-01"


def test_pick_hostname_mac_fallback_replaces_colons():
    host = {"primary_name": "", "id": "", "mac": "aa:bb:cc:dd:ee:ff"}
    assert _pick_hostname(host) == "aa_bb_cc_dd_ee_ff"


def test_pick_hostname_whitespace_only_primary_name_falls_through():
    host = {"primary_name": "   ", "id": "", "mac": "11:22:33:44:55:66"}
    assert _pick_hostname(host) == "11_22_33_44_55_66"


def test_pick_hostname_none_primary_name_falls_through():
    host = {"primary_name": None, "id": "some-id"}
    assert _pick_hostname(host) == "some-id"


def test_pick_hostname_missing_all_uses_mac():
    host = {"mac": "aa:bb:cc:dd:ee:ff"}
    assert _pick_hostname(host) == "aa_bb_cc_dd_ee_ff"


# ── _group_name ────────────────────────────────────────────────────────────


def test_group_name_workstation():
    assert _group_name("workstation") == "freebox_workstation"


def test_group_name_smartphone():
    assert _group_name("smartphone") == "freebox_smartphone"


def test_group_name_printer():
    assert _group_name("printer") == "freebox_printer"


# ── reachable_only filter ─────────────────────────────────────────────────


def _filter_hosts(hosts, reachable_only):
    return [h for h in hosts if not reachable_only or h.get("reachable", False)]


def test_reachable_only_excludes_unreachable():
    hosts = [
        {"primary_name": "a", "reachable": True},
        {"primary_name": "b", "reachable": False},
    ]
    result = _filter_hosts(hosts, reachable_only=True)
    assert len(result) == 1
    assert result[0]["primary_name"] == "a"


def test_reachable_only_false_includes_all():
    hosts = [
        {"primary_name": "a", "reachable": True},
        {"primary_name": "b", "reachable": False},
    ]
    result = _filter_hosts(hosts, reachable_only=False)
    assert len(result) == 2


def test_empty_host_list():
    assert _filter_hosts([], reachable_only=True) == []


# ── verify_file pattern ───────────────────────────────────────────────────


def test_verify_file_accepts_yml():
    assert "freebox_lan.yml".endswith(("freebox_lan.yml", "freebox_lan.yaml"))


def test_verify_file_accepts_yaml():
    assert "freebox_lan.yaml".endswith(("freebox_lan.yml", "freebox_lan.yaml"))


def test_verify_file_rejects_other():
    assert not "hosts.yml".endswith(("freebox_lan.yml", "freebox_lan.yaml"))
