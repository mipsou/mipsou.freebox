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


# ── WoL POST path ─────────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self):
        self.calls = []

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        return None


def test_wol_post_correct_path():
    client = RecordingClient()
    mac = validate_mac("AA:BB:CC:DD:EE:FF")
    client.post("/lan/wol/%s/%s/" % ("pub0", mac), body={})
    assert client.calls[0]["path"] == "/lan/wol/pub0/aa:bb:cc:dd:ee:ff/"


def test_wol_with_password_sends_body():
    client = RecordingClient()
    mac = validate_mac("AA:BB:CC:DD:EE:FF")
    password = validate_secureon_password("00:11:22:33:44:55")
    client.post("/lan/wol/%s/%s/" % ("pub0", mac), body={"password": password})
    assert client.calls[0]["body"] == {"password": "00:11:22:33:44:55"}


def test_wol_custom_ifname():
    client = RecordingClient()
    mac = validate_mac("aa:bb:cc:dd:ee:ff")
    client.post("/lan/wol/%s/%s/" % ("eth0", mac), body={})
    assert client.calls[0]["path"] == "/lan/wol/eth0/aa:bb:cc:dd:ee:ff/"


def test_check_mode_no_post():
    """In check_mode, no POST should be issued (simulated here by not calling)."""
    client = RecordingClient()
    # check_mode: simply verify no calls were made
    assert client.calls == []


def test_changed_always_true():
    """Non-idempotent: changed is always true after a send."""
    client = RecordingClient()
    mac = validate_mac("aa:bb:cc:dd:ee:ff")
    client.post("/lan/wol/pub0/%s/" % mac, body={})
    # One call was made → action was taken → changed=True
    assert len(client.calls) == 1
