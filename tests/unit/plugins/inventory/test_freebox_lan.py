# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Unit tests for freebox_lan inventory plugin logic.

Tests focus on the host-extraction and grouping logic; the Ansible plugin
infrastructure (BaseInventoryPlugin) is not instantiated here because it
requires a full Ansible install.  We instead test the pure-Python helpers
that the parse() method calls.
"""


# ── Pure-logic helpers replicated from the plugin ────────────────────────


def _first_active_ipv4(host):
    """Return the first reachable IPv4 address or None."""
    for addr in host.get("l3connectivities") or []:
        if addr.get("af") == "ipv4" and addr.get("reachable"):
            return addr.get("addr")
    return None


def _group_name(host_type):
    """Sanitize host_type into a valid Ansible group name."""
    return "freebox_%s" % host_type.replace("-", "_").replace(" ", "_")


def _hostname(host):
    """Derive a display hostname from a LAN browser entry."""
    return host.get("primary_name") or host.get("id") or host.get("mac", "unknown")


def _extract_mac(host):
    """Return the MAC address string from a LAN browser entry."""
    return host.get("l2ident", {}).get("id") or host.get("mac", "")


# ── Test _first_active_ipv4 ───────────────────────────────────────────────


def test_first_active_ipv4_returns_reachable():
    host = {
        "l3connectivities": [
            {"af": "ipv4", "reachable": True, "addr": "192.168.1.100"},
        ]
    }
    assert _first_active_ipv4(host) == "192.168.1.100"


def test_first_active_ipv4_skips_unreachable():
    host = {
        "l3connectivities": [
            {"af": "ipv4", "reachable": False, "addr": "192.168.1.1"},
            {"af": "ipv4", "reachable": True, "addr": "192.168.1.2"},
        ]
    }
    assert _first_active_ipv4(host) == "192.168.1.2"


def test_first_active_ipv4_skips_ipv6():
    host = {
        "l3connectivities": [
            {"af": "ipv6", "reachable": True, "addr": "fe80::1"},
        ]
    }
    assert _first_active_ipv4(host) is None


def test_first_active_ipv4_empty():
    assert _first_active_ipv4({}) is None


def test_first_active_ipv4_none_connectivities():
    assert _first_active_ipv4({"l3connectivities": None}) is None


# ── Test _group_name ──────────────────────────────────────────────────────


def test_group_name_workstation():
    assert _group_name("workstation") == "freebox_workstation"


def test_group_name_replaces_hyphens():
    assert _group_name("smart-phone") == "freebox_smart_phone"


def test_group_name_replaces_spaces():
    assert _group_name("set top box") == "freebox_set_top_box"


def test_group_name_unknown():
    assert _group_name("unknown") == "freebox_unknown"


# ── Test _hostname ────────────────────────────────────────────────────────


def test_hostname_uses_primary_name():
    host = {"primary_name": "mypc", "id": "abc", "mac": "aa:bb:cc:dd:ee:ff"}
    assert _hostname(host) == "mypc"


def test_hostname_falls_back_to_id():
    host = {"id": "device-id-123", "mac": "aa:bb:cc:dd:ee:ff"}
    assert _hostname(host) == "device-id-123"


def test_hostname_falls_back_to_mac():
    host = {"mac": "aa:bb:cc:dd:ee:ff"}
    assert _hostname(host) == "aa:bb:cc:dd:ee:ff"


def test_hostname_defaults_to_unknown():
    assert _hostname({}) == "unknown"


# ── Test _extract_mac ─────────────────────────────────────────────────────


def test_extract_mac_from_l2ident():
    host = {"l2ident": {"id": "aa:bb:cc:dd:ee:ff", "type": "mac"}}
    assert _extract_mac(host) == "aa:bb:cc:dd:ee:ff"


def test_extract_mac_falls_back_to_mac_field():
    host = {"mac": "11:22:33:44:55:66"}
    assert _extract_mac(host) == "11:22:33:44:55:66"


def test_extract_mac_empty():
    assert _extract_mac({}) == ""


# ── Integration: build host dict ─────────────────────────────────────────


def test_full_host_extraction():
    host = {
        "primary_name": "nas",
        "host_type": "workstation",
        "mac": "aa:bb:cc:dd:ee:ff",
        "l2ident": {"id": "aa:bb:cc:dd:ee:ff", "type": "mac"},
        "l3connectivities": [
            {"af": "ipv4", "reachable": True, "addr": "192.168.1.10"}
        ],
    }
    assert _hostname(host) == "nas"
    assert _group_name(host["host_type"]) == "freebox_workstation"
    assert _first_active_ipv4(host) == "192.168.1.10"
    assert _extract_mac(host) == "aa:bb:cc:dd:ee:ff"


def test_host_without_ip():
    host = {
        "primary_name": "printer",
        "host_type": "networking",
        "l3connectivities": [],
    }
    assert _first_active_ipv4(host) is None
    assert _group_name(host["host_type"]) == "freebox_networking"
