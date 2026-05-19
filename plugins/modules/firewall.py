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
module: firewall
short_description: Manage Freebox DMZ and read firewall incoming rules
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Manage the Freebox DMZ configuration (singleton) via read-modify-write.
  - Expose the list of incoming firewall rules as C(ansible_facts.freebox_firewall_incoming)
    (read-only).
  - The C(enabled) and C(ip) fields on the DMZ are the only writable fields.
options:
  enabled:
    description:
      - Whether the DMZ is active. Omit to leave the current value unchanged.
    type: bool
  ip:
    description:
      - Target IPv4 address for DMZ traffic. Must be in RFC1918 private space.
        Omit to leave unchanged.
    type: str
  gather_facts:
    description:
      - When C(true), fetch and return the incoming firewall rules as
        C(ansible_facts.freebox_firewall_incoming).
    type: bool
    default: false
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Enable DMZ to the reverse proxy
  mipsou.freebox.firewall:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: true
    ip: 192.168.1.50

- name: Disable DMZ
  mipsou.freebox.firewall:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: false

- name: Gather incoming firewall rules
  mipsou.freebox.firewall:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    gather_facts: true
  register: fw
# fw.ansible_facts.freebox_firewall_incoming is a list of rule dicts
"""

RETURN = r"""
dmz:
  description: Current DMZ configuration after the call.
  type: dict
  returned: always
changed:
  description: Whether the Freebox DMZ state was modified.
  type: bool
  returned: always
ansible_facts:
  description: Populated when I(gather_facts=true).
  type: dict
  returned: when gather_facts=true
  contains:
    freebox_firewall_incoming:
      description: List of incoming firewall rules.
      type: list
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
    validate_rfc1918,
)


def _update_dmz(client, desired, check_mode=False):
    """Read-modify-write the DMZ config. Returns (changed, before, after)."""
    if desired:
        return client.diff_and_put("/fw/dmz/", desired, full_body=False, check_mode=check_mode)
    dmz = client.get("/fw/dmz/") or {}
    return False, dmz, dmz


def _collect_incoming(client):
    """Return the list of incoming firewall rules."""
    return client.get("/fw/incoming/") or []


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        enabled=dict(type="bool"),
        ip=dict(type="str"),
        gather_facts=dict(type="bool", default=False),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    ip_raw = module.params.get("ip")
    if ip_raw is not None:
        try:
            ip_raw = validate_rfc1918(ip_raw)
        except ValueError as exc:
            module.fail_json(msg="invalid ip: %s" % exc)

    desired = {}
    if module.params.get("enabled") is not None:
        desired["enabled"] = module.params["enabled"]
    if ip_raw is not None:
        desired["ip"] = ip_raw

    client = FreeboxClient(module)
    try:
        changed, _before, dmz = _update_dmz(client, desired, module.check_mode)
        result = dict(changed=changed, dmz=dmz)

        if module.params.get("gather_facts"):
            result["ansible_facts"] = {"freebox_firewall_incoming": _collect_incoming(client)}

    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
