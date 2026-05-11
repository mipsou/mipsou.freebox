# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import (
    dhcp_config as mod,
)


def test_build_desired_drops_none_values():
    params = dict(
        enabled=True,
        sticky_assign=None,
        ip_range_start="192.168.1.100",
        ip_range_end=None,
        always_broadcast=None,
        dns=["1.1.1.1"],
    )
    assert mod._build_desired(params) == {
        "enabled": True,
        "ip_range_start": "192.168.1.100",
        "dns": ["1.1.1.1"],
    }


def test_build_desired_preserves_explicit_false_and_empty_list():
    # Explicit False / [] must not be dropped — only None.
    params = dict(
        enabled=False,
        sticky_assign=True,
        ip_range_start=None,
        ip_range_end=None,
        always_broadcast=False,
        dns=[],
    )
    assert mod._build_desired(params) == {
        "enabled": False,
        "sticky_assign": True,
        "always_broadcast": False,
        "dns": [],
    }


def test_compute_diff_only_lists_changed_keys():
    before = {"enabled": True, "dns": ["1.1.1.1"], "sticky_assign": False}
    after = {"enabled": True, "dns": ["9.9.9.9"], "sticky_assign": True}
    diff = mod._compute_diff(before, after, ("enabled", "dns", "sticky_assign"))
    assert diff == {
        "dns": (["1.1.1.1"], ["9.9.9.9"]),
        "sticky_assign": (False, True),
    }


def test_compute_diff_skips_keys_not_in_filter():
    before = {"enabled": True, "ip_range_start": "192.168.1.10"}
    after = {"enabled": False, "ip_range_start": "192.168.1.20"}
    # Only inspect 'enabled' — ip_range_start change is invisible.
    assert mod._compute_diff(before, after, ("enabled",)) == {"enabled": (True, False)}
