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
module: dhcp_config
short_description: Manage the Freebox global DHCP server configuration
version_added: "0.2.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the Freebox singleton DHCP configuration. Only
    parameters explicitly set on the task are sent to the API; unspecified
    parameters keep their current Freebox-side value.
  - The fields C(gateway) and C(netmask) are read-only on the Freebox API
    and cannot be changed by this module.
  - To manage DHCP options (e.g. C(tftp_server_name) for PXE boot), a
    dedicated C(dhcp_option) module will be added in a later release.
options:
  enabled:
    description:
      - Whether the Freebox DHCP server is active.
    type: bool
  sticky_assign:
    description:
      - When true, the Freebox tries to keep the same dynamic IP for each MAC
        across lease renewals.
    type: bool
  ip_range_start:
    description:
      - First IP of the dynamic DHCP pool. Must be in RFC1918 private space
        and not end in C(.0), C(.1), C(.254) or C(.255) (Freebox-reserved).
    type: str
  ip_range_end:
    description:
      - Last IP of the dynamic DHCP pool. Same constraints as I(ip_range_start).
    type: str
  always_broadcast:
    description:
      - Whether all DHCP replies are broadcast instead of unicast.
    type: bool
  dns:
    description:
      - Custom DNS servers advertised to DHCP clients. Empty list = use the
        Freebox default DNS.
    type: list
    elements: str
"""

EXAMPLES = r"""
- name: Pin the DHCP pool and enable sticky assignments
  mipsou.freebox.dhcp_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: true
    sticky_assign: true
    ip_range_start: 192.168.1.100
    ip_range_end: 192.168.1.200
    dns:
      - 1.1.1.1
      - 9.9.9.9

- name: Disable the Freebox DHCP server (run another one in the LAN)
  mipsou.freebox.dhcp_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: false
"""

RETURN = r"""
config:
  description: The full DHCP configuration after the call (including read-only fields).
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
    validate_dhcp_ip,
)


_SETTABLE_KEYS = (
    "enabled",
    "sticky_assign",
    "ip_range_start",
    "ip_range_end",
    "always_broadcast",
    "dns",
)


def _build_desired(params):
    """Return only the keys the user explicitly set (non-None)."""
    return {k: params[k] for k in _SETTABLE_KEYS if params.get(k) is not None}


def _compute_diff(before, after, keys):
    """Return ``{key: (before, after)}`` for keys whose value changed."""
    return {k: (before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)}


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        enabled=dict(type="bool"),
        sticky_assign=dict(type="bool"),
        ip_range_start=dict(type="str"),
        ip_range_end=dict(type="str"),
        always_broadcast=dict(type="bool"),
        dns=dict(type="list", elements="str"),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    for key in ("ip_range_start", "ip_range_end"):
        value = module.params.get(key)
        if value is None:
            continue
        try:
            validate_dhcp_ip(value)
        except ValueError as exc:
            module.fail_json(msg="invalid %s: %s" % (key, exc))

    desired = _build_desired(module.params)

    client = FreeboxClient(module)
    try:
        changed, before, after = client.diff_and_put(
            "/dhcp/config/",
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
