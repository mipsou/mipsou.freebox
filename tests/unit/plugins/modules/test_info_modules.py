# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Unit tests for read-only info_* modules.

Each test calls the module's _collect_facts(client) helper directly,
which is the extracted pure-logic function backed by a RecordingClient.
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


# ── Shared RecordingClient ────────────────────────────────────────────────


class RecordingClient(object):
    """Returns fixed data per path; raises for unexpected paths."""

    def __init__(self, data):
        self._data = data
        self.calls = []

    def get(self, path, query=None):
        self.calls.append(path)
        if path not in self._data:
            raise AssertionError("unexpected GET %s" % path)
        return self._data[path]


# ── info_storage._collect_facts ───────────────────────────────────────────


def test_info_storage_returns_all_three_keys():
    client = RecordingClient({
        "/storage/disk/": [{"id": 1, "type": "hdd"}],
        "/storage/partition/": [{"id": "p1"}],
        "/storage/raid/": [],
    })
    facts = info_storage._collect_facts(client)
    assert facts["disks"] == [{"id": 1, "type": "hdd"}]
    assert facts["partitions"] == [{"id": "p1"}]
    assert facts["raid"] == []


def test_info_storage_empty():
    client = RecordingClient({
        "/storage/disk/": [],
        "/storage/partition/": [],
        "/storage/raid/": [],
    })
    facts = info_storage._collect_facts(client)
    assert facts["disks"] == []


def test_info_storage_hits_three_endpoints():
    client = RecordingClient({
        "/storage/disk/": [],
        "/storage/partition/": [],
        "/storage/raid/": [],
    })
    info_storage._collect_facts(client)
    assert set(client.calls) == {"/storage/disk/", "/storage/partition/", "/storage/raid/"}


# ── info_vpn._collect_facts ───────────────────────────────────────────────


def test_info_vpn_returns_three_keys():
    client = RecordingClient({
        "/vpn/status/": {"enabled": True},
        "/vpn/connection/": [{"id": "c1"}],
        "/vpn/client/config/": [{"id": "cfg1"}],
    })
    facts = info_vpn._collect_facts(client)
    assert facts["status"] == {"enabled": True}
    assert facts["connections"] == [{"id": "c1"}]
    assert facts["client_configs"] == [{"id": "cfg1"}]


def test_info_vpn_empty_connections():
    client = RecordingClient({
        "/vpn/status/": {},
        "/vpn/connection/": [],
        "/vpn/client/config/": [],
    })
    facts = info_vpn._collect_facts(client)
    assert facts["connections"] == []


def test_info_vpn_hits_three_endpoints():
    client = RecordingClient({
        "/vpn/status/": {},
        "/vpn/connection/": [],
        "/vpn/client/config/": [],
    })
    info_vpn._collect_facts(client)
    assert set(client.calls) == {"/vpn/status/", "/vpn/connection/", "/vpn/client/config/"}


# ── info_switch._collect_facts ────────────────────────────────────────────


def test_info_switch_enriches_with_stats():
    client = RecordingClient({
        "/switch/port/": [{"id": 1, "link": "up"}],
        "/switch/port/1/stats": {"rx_bytes": 1000},
    })
    facts = info_switch._collect_facts(client)
    assert facts["ports"][0]["stats"] == {"rx_bytes": 1000}


def test_info_switch_no_ports():
    client = RecordingClient({"/switch/port/": []})
    facts = info_switch._collect_facts(client)
    assert facts["ports"] == []


def test_info_switch_multiple_ports():
    client = RecordingClient({
        "/switch/port/": [{"id": 1}, {"id": 2}],
        "/switch/port/1/stats": {"rx_bytes": 100},
        "/switch/port/2/stats": {"rx_bytes": 200},
    })
    facts = info_switch._collect_facts(client)
    assert facts["ports"][0]["stats"]["rx_bytes"] == 100
    assert facts["ports"][1]["stats"]["rx_bytes"] == 200


# ── info_calls._collect_facts ─────────────────────────────────────────────


def test_info_calls_returns_log():
    client = RecordingClient({"/call/log/": [{"id": 1, "type": "missed"}]})
    facts = info_calls._collect_facts(client)
    assert facts == [{"id": 1, "type": "missed"}]
    assert "/call/log/" in client.calls


def test_info_calls_empty():
    client = RecordingClient({"/call/log/": []})
    assert info_calls._collect_facts(client) == []


# ── info_contacts._collect_facts ──────────────────────────────────────────


def test_info_contacts_returns_list():
    client = RecordingClient({"/contact/": [{"id": 1, "first_name": "Alice"}]})
    facts = info_contacts._collect_facts(client)
    assert facts[0]["first_name"] == "Alice"
    assert "/contact/" in client.calls


def test_info_contacts_empty():
    client = RecordingClient({"/contact/": []})
    assert info_contacts._collect_facts(client) == []


# ── info_tv._collect_facts ────────────────────────────────────────────────


def test_info_tv_returns_records():
    client = RecordingClient({"/pvr/record/": [{"id": 1, "name": "News"}]})
    facts = info_tv._collect_facts(client)
    assert facts == [{"id": 1, "name": "News"}]
    assert "/pvr/record/" in client.calls


def test_info_tv_empty():
    client = RecordingClient({"/pvr/record/": []})
    assert info_tv._collect_facts(client) == []


# ── info_shares._collect_facts ────────────────────────────────────────────


def test_info_shares_returns_three_protocols():
    client = RecordingClient({
        "/ftp/config/": {"enabled": True},
        "/afp/config/": {"enabled": False},
        "/tftp/config/": {"enabled": False},
    })
    facts = info_shares._collect_facts(client)
    assert facts["ftp"] == {"enabled": True}
    assert facts["afp"] == {"enabled": False}
    assert facts["tftp"] == {"enabled": False}


def test_info_shares_hits_three_endpoints():
    client = RecordingClient({
        "/ftp/config/": {},
        "/afp/config/": {},
        "/tftp/config/": {},
    })
    info_shares._collect_facts(client)
    assert set(client.calls) == {"/ftp/config/", "/afp/config/", "/tftp/config/"}


# ── info_dyndns._collect_facts ────────────────────────────────────────────


def test_info_dyndns_returns_list():
    client = RecordingClient({"/dyndns/": [{"provider": "ovh", "enabled": True}]})
    facts = info_dyndns._collect_facts(client)
    assert facts == [{"provider": "ovh", "enabled": True}]
    assert "/dyndns/" in client.calls


def test_info_dyndns_empty():
    client = RecordingClient({"/dyndns/": []})
    assert info_dyndns._collect_facts(client) == []
