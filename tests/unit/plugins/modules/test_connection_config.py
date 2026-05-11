# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import (
    connection_config as mod,
)


def test_build_desired_drops_none_values():
    params = dict(
        ping=True,
        remote_access=None,
        remote_access_port=None,
        wol_port=8080,
        adblock=False,
    )
    assert mod._build_desired(params) == {
        "ping": True,
        "wol_port": 8080,
        "adblock": False,
    }


def test_compute_diff_lists_only_changed_keys():
    before = {"ping": True, "wol_port": 9, "remote_access": False}
    after = {"ping": False, "wol_port": 9, "remote_access": True}
    diff = mod._compute_diff(before, after, ("ping", "wol_port", "remote_access"))
    assert diff == {
        "ping": (True, False),
        "remote_access": (False, True),
    }
