#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: connection_config
short_description: Manage the Freebox WAN connection configuration
version_added: "0.2.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the singleton WAN connection configuration. Only
    parameters explicitly set on the task are sent to the API; unspecified
    parameters keep their current Freebox-side value.
  - C(remote_access_ip) and C(is_secure_pass) are read-only on the Freebox
    API and cannot be changed through this module.
options:
  ping:
    description:
      - Whether the Freebox responds to ICMP echo from the WAN interface.
    type: bool
  remote_access:
    description:
      - Whether the Freebox OS web UI is reachable from the WAN.
    type: bool
  remote_access_port:
    description:
      - TCP port exposed on the WAN for the remote-access web UI. Must be
        in 1..65535 when set.
    type: int
  wol_port:
    description:
      - UDP port the Freebox listens on for Wake-on-LAN magic packets coming
        from the WAN. Must be in 1..65535 when set.
    type: int
  adblock:
    description:
      - Whether the Freebox built-in ad-blocking is enabled at the
        connection level.
    type: bool
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Enable remote access on a non-default port
  mipsou.freebox.connection_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    remote_access: true
    remote_access_port: 56443

- name: Disable WAN ping and adblock
  mipsou.freebox.connection_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    ping: false
    adblock: false
"""

RETURN = r"""
config:
  description: The full connection configuration after the call.
  type: dict
  returned: always
diff:
  description: Mapping of changed keys to their (before, after) values.
  type: dict
  returned: always
changed:
  description: Whether the Freebox state was modified.
  type: bool
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
    validate_port,
)


_SETTABLE_KEYS = (
    "ping",
    "remote_access",
    "remote_access_port",
    "wol_port",
    "adblock",
)


def _build_desired(params):
    return {k: params[k] for k in _SETTABLE_KEYS if params.get(k) is not None}


def _compute_diff(before, after, keys):
    return {k: (before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)}


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        ping=dict(type="bool"),
        remote_access=dict(type="bool"),
        remote_access_port=dict(type="int"),
        wol_port=dict(type="int"),
        adblock=dict(type="bool"),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    for key in ("remote_access_port", "wol_port"):
        value = module.params.get(key)
        if value is None:
            continue
        try:
            validate_port(value, key)
        except ValueError as exc:
            module.fail_json(msg=str(exc))

    desired = _build_desired(module.params)

    client = FreeboxClient(module)
    try:
        changed, before, after = client.diff_and_put(
            "/connection/config/",
            desired,
            full_body=False,
            check_mode=module.check_mode,
        )
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    diff = _compute_diff(before, after, desired.keys())
    module.exit_json(changed=changed, config=after, diff=diff)


if __name__ == "__main__":
    main()
