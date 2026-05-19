# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.mipsou.freebox.plugins.modules import wakeup as mod
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    validate_mac,
    validate_secureon_password,
)


# ── RecordingClient ───────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self):
        self.calls = []

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        return None


# ── validate_mac ─────────────────────────────────────────────────────────


def test_validate_mac_normalizes_to_lowercase_colon():
    assert validate_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"


def test_validate_mac_accepts_colon_format():
    assert validate_mac("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:dd:ee:ff"


def test_validate_mac_rejects_bad_format():
    with pytest.raises(ValueError):
        validate_mac("not-a-mac")


def test_validate_mac_rejects_short():
    with pytest.raises(ValueError):
        validate_mac("aa:bb:cc:dd:ee")


# ── validate_secureon_password ────────────────────────────────────────────


def test_secureon_accepts_mac_format():
    assert validate_secureon_password("00:11:22:33:44:55") == "00:11:22:33:44:55"


def test_secureon_accepts_hyphen_format():
    assert validate_secureon_password("00-11-22-33-44-55") == "00:11:22:33:44:55"


def test_secureon_rejects_invalid():
    with pytest.raises(ValueError):
        validate_secureon_password("notvalid")


# ── mod._send_wol ─────────────────────────────────────────────────────────


def test_send_wol_correct_path():
    client = RecordingClient()
    mac = validate_mac("AA:BB:CC:DD:EE:FF")
    mod._send_wol(client, "pub0", mac)
    assert client.calls[0]["path"] == "/lan/wol/pub0/aa:bb:cc:dd:ee:ff/"


def test_send_wol_with_password_sends_body():
    client = RecordingClient()
    mac = validate_mac("AA:BB:CC:DD:EE:FF")
    password = validate_secureon_password("00:11:22:33:44:55")
    mod._send_wol(client, "pub0", mac, {"password": password})
    assert client.calls[0]["body"] == {"password": "00:11:22:33:44:55"}


def test_send_wol_custom_ifname():
    client = RecordingClient()
    mac = validate_mac("aa:bb:cc:dd:ee:ff")
    mod._send_wol(client, "eth0", mac)
    assert client.calls[0]["path"] == "/lan/wol/eth0/aa:bb:cc:dd:ee:ff/"


def test_send_wol_empty_body_when_no_password():
    client = RecordingClient()
    mac = validate_mac("aa:bb:cc:dd:ee:ff")
    mod._send_wol(client, "pub0", mac)
    assert client.calls[0]["body"] == {}


def test_send_wol_issues_exactly_one_post():
    client = RecordingClient()
    mac = validate_mac("aa:bb:cc:dd:ee:ff")
    mod._send_wol(client, "pub0", mac)
    assert len(client.calls) == 1
    assert client.calls[0]["method"] == "POST"
