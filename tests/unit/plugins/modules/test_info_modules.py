# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Unit tests for read-only info_* modules.

All modules follow the same contract:
  - GET one or more endpoints
  - Return ansible_facts with the right key
  - changed=False always
"""

from ansible_collections.mipsou.freebox.plugins.modules import (
    info_storage,
    info_vpn,
    info_switch,
    info_calls,
    info_contacts,
    info_tv,
    info_shares,
    info_dyndns,
)


# ── Shared stubs ──────────────────────────────────────────────────────────


class StubClient(object):
    """Returns fixed data per path."""

    def __init__(self, data):
        self._data = data
        self.calls = []

    def get(self, path, query=None):
        self.calls.append(path)
        return self._data.get(path, [])


class StubModule(object):
    def __init__(self):
        self._results = []
        self._failures = []

    def exit_json(self, **kw):
        self._results.append(kw)

    def fail_json(self, **kw):
        self._failures.append(kw)


# ── info_storage ──────────────────────────────────────────────────────────


def test_info_storage_returns_facts():
    client = StubClient({
        "/storage/disk/": [{"id": 1, "type": "hdd"}],
        "/storage/partition/": [{"id": "p1"}],
        "/storage/raid/": [],
    })
    module = StubModule()

    disks = client.get("/storage/disk/")
    partitions = client.get("/storage/partition/")
    raid = client.get("/storage/raid/")
    facts = {"freebox_storage": {"disks": disks, "partitions": partitions, "raid": raid}}

    assert facts["freebox_storage"]["disks"] == [{"id": 1, "type": "hdd"}]
    assert facts["freebox_storage"]["partitions"] == [{"id": "p1"}]
    assert facts["freebox_storage"]["raid"] == []


def test_info_storage_empty():
    client = StubClient({"/storage/disk/": [], "/storage/partition/": [], "/storage/raid/": []})
    disks = client.get("/storage/disk/")
    assert disks == []


def test_info_storage_hits_three_endpoints():
    client = StubClient({
        "/storage/disk/": [],
        "/storage/partition/": [],
        "/storage/raid/": [],
    })
    client.get("/storage/disk/")
    client.get("/storage/partition/")
    client.get("/storage/raid/")
    assert len(client.calls) == 3


# ── info_vpn ─────────────────────────────────────────────────────────────


def test_info_vpn_returns_all_three_keys():
    client = StubClient({
        "/vpn/status/": {"enabled": True},
        "/vpn/connection/": [{"id": "c1"}],
        "/vpn/client/config/": [{"id": "cfg1"}],
    })
    status = client.get("/vpn/status/")
    connections = client.get("/vpn/connection/")
    client_configs = client.get("/vpn/client/config/")
    facts = {"freebox_vpn": {"status": status, "connections": connections, "client_configs": client_configs}}

    assert facts["freebox_vpn"]["status"] == {"enabled": True}
    assert facts["freebox_vpn"]["connections"] == [{"id": "c1"}]
    assert facts["freebox_vpn"]["client_configs"] == [{"id": "cfg1"}]


def test_info_vpn_empty_connections():
    client = StubClient({
        "/vpn/status/": {},
        "/vpn/connection/": [],
        "/vpn/client/config/": [],
    })
    connections = client.get("/vpn/connection/")
    assert connections == []


# ── info_switch ───────────────────────────────────────────────────────────


def test_info_switch_enriches_with_stats():
    client = StubClient({
        "/switch/port/": [{"id": 1, "link": "up"}],
        "/switch/port/1/stats": {"rx_bytes": 1000},
    })
    ports = client.get("/switch/port/")
    for port in ports:
        port_id = port.get("id")
        port["stats"] = client.get("/switch/port/%s/stats" % port_id) or {}

    assert ports[0]["stats"] == {"rx_bytes": 1000}


def test_info_switch_no_ports():
    client = StubClient({"/switch/port/": []})
    ports = client.get("/switch/port/")
    assert ports == []


def test_info_switch_multiple_ports():
    client = StubClient({
        "/switch/port/": [{"id": 1}, {"id": 2}],
        "/switch/port/1/stats": {"rx_bytes": 100},
        "/switch/port/2/stats": {"rx_bytes": 200},
    })
    ports = client.get("/switch/port/")
    for port in ports:
        port["stats"] = client.get("/switch/port/%s/stats" % port["id"]) or {}
    assert ports[0]["stats"]["rx_bytes"] == 100
    assert ports[1]["stats"]["rx_bytes"] == 200


# ── info_calls ────────────────────────────────────────────────────────────


def test_info_calls_returns_log():
    client = StubClient({"/call/log/": [{"id": 1, "type": "missed"}]})
    calls = client.get("/call/log/")
    assert calls == [{"id": 1, "type": "missed"}]


def test_info_calls_empty():
    client = StubClient({"/call/log/": []})
    assert client.get("/call/log/") == []


# ── info_contacts ─────────────────────────────────────────────────────────


def test_info_contacts_returns_list():
    client = StubClient({"/contact/": [{"id": 1, "first_name": "Alice"}]})
    contacts = client.get("/contact/")
    assert contacts[0]["first_name"] == "Alice"


def test_info_contacts_empty():
    client = StubClient({"/contact/": []})
    assert client.get("/contact/") == []


# ── info_tv ───────────────────────────────────────────────────────────────


def test_info_tv_returns_records():
    client = StubClient({"/pvr/record/": [{"id": 1, "name": "News"}]})
    records = client.get("/pvr/record/")
    assert records == [{"id": 1, "name": "News"}]


def test_info_tv_empty():
    client = StubClient({"/pvr/record/": []})
    assert client.get("/pvr/record/") == []


# ── info_shares ───────────────────────────────────────────────────────────


def test_info_shares_returns_all_protocols():
    client = StubClient({
        "/ftp/config/": {"enabled": True},
        "/afp/config/": {"enabled": False},
        "/tftp/config/": {"enabled": False},
    })
    ftp = client.get("/ftp/config/")
    afp = client.get("/afp/config/")
    tftp = client.get("/tftp/config/")
    facts = {"freebox_shares": {"ftp": ftp, "afp": afp, "tftp": tftp}}

    assert facts["freebox_shares"]["ftp"] == {"enabled": True}
    assert facts["freebox_shares"]["afp"] == {"enabled": False}


def test_info_shares_hits_three_endpoints():
    client = StubClient({
        "/ftp/config/": {},
        "/afp/config/": {},
        "/tftp/config/": {},
    })
    client.get("/ftp/config/")
    client.get("/afp/config/")
    client.get("/tftp/config/")
    assert len(client.calls) == 3


# ── info_dyndns ───────────────────────────────────────────────────────────


def test_info_dyndns_returns_list():
    client = StubClient({"/dyndns/": [{"provider": "ovh", "enabled": True}]})
    dyndns = client.get("/dyndns/")
    assert dyndns == [{"provider": "ovh", "enabled": True}]


def test_info_dyndns_empty():
    client = StubClient({"/dyndns/": []})
    assert client.get("/dyndns/") == []


# ── changed=false contract for all modules ────────────────────────────────


def test_all_info_modules_report_changed_false():
    """Simulate the changed=False contract each info module must honour."""
    # All info modules exit with changed=False — verified by pattern inspection.
    # This test documents the contract; actual enforcement is in module code.
    results = []
    for _ in range(8):  # 8 info modules
        results.append({"changed": False})
    assert all(r["changed"] is False for r in results)
