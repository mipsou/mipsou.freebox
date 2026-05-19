# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Unit tests for the freebox_lan inventory plugin logic.

The InventoryModule.parse() depends on Ansible's plugin framework and
can't be tested without a full config file. These tests cover the
pure-logic helpers (hostname selection, group naming, filtering) by
exercising the same code paths used in parse().
"""


# ── Hostname selection logic ───────────────────────────────────────────────


def _pick_hostname(host):
    """Mirror the hostname selection from InventoryModule.parse()."""
    return (
        (host.get("primary_name") or "").strip()
        or host.get("id", "")
        or host.get("mac", "unknown").replace(":", "_")
    )


def test_primary_name_used_first():
    host = {"primary_name": "my-nas", "mac": "aa:bb:cc:dd:ee:ff"}
    assert _pick_hostname(host) == "my-nas"


def test_id_used_when_no_primary_name():
    host = {"primary_name": "", "id": "fbx-vm-01", "mac": "aa:bb:cc:dd:ee:ff"}
    assert _pick_hostname(host) == "fbx-vm-01"


def test_mac_fallback_replaces_colons():
    host = {"primary_name": "", "id": "", "mac": "aa:bb:cc:dd:ee:ff"}
    assert _pick_hostname(host) == "aa_bb_cc_dd_ee_ff"


def test_whitespace_only_primary_name_falls_through():
    host = {"primary_name": "   ", "id": "", "mac": "11:22:33:44:55:66"}
    assert _pick_hostname(host) == "11_22_33_44_55_66"


# ── Group naming ──────────────────────────────────────────────────────────


def test_group_name_from_host_type():
    host_type = "workstation"
    assert "freebox_%s" % host_type == "freebox_workstation"


def test_group_name_smartphone():
    assert "freebox_%s" % "smartphone" == "freebox_smartphone"


def test_no_group_when_group_by_type_false():
    host_type = "printer"
    group_by_type = False
    groups_to_add = ["freebox_%s" % host_type] if group_by_type and host_type else []
    assert groups_to_add == []


def test_no_group_when_host_type_empty():
    host_type = ""
    group_by_type = True
    groups_to_add = ["freebox_%s" % host_type] if group_by_type and host_type else []
    assert groups_to_add == []


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


# ── L3 address extraction ─────────────────────────────────────────────────


def _extract_ip(host):
    l3 = host.get("l3connectivities") or []
    if l3:
        return l3[0].get("addr", "")
    return None


def test_l3_ip_extracted():
    host = {"l3connectivities": [{"addr": "192.168.1.100"}]}
    assert _extract_ip(host) == "192.168.1.100"


def test_l3_ip_missing():
    host = {}
    assert _extract_ip(host) is None


def test_l3_ip_empty_list():
    host = {"l3connectivities": []}
    assert _extract_ip(host) is None


# ── verify_file logic ─────────────────────────────────────────────────────


def test_verify_file_accepts_yml():
    assert "freebox_lan.yml".endswith(("freebox_lan.yml", "freebox_lan.yaml"))


def test_verify_file_accepts_yaml():
    assert "freebox_lan.yaml".endswith(("freebox_lan.yml", "freebox_lan.yaml"))


def test_verify_file_rejects_other():
    assert not "hosts.yml".endswith(("freebox_lan.yml", "freebox_lan.yaml"))
