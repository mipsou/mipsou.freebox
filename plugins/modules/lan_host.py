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
module: lan_host
short_description: Update the display name and type of a Freebox LAN host
version_added: "0.2.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Look up a LAN host by MAC address and optionally update its C(primary_name)
    and/or C(host_type) (C(PUT /lan/browser/pub/{id})).
  - When called with only C(mac) and no optional parameters the module performs a
    read-only lookup and returns the current host dict with C(changed=false).
  - The Freebox assigns its own ID to each discovered device — you never need to
    know it.
  - This module does not create or delete hosts. The Freebox manages the device
    lifecycle automatically (devices appear when they connect and persist until
    manually removed from the UI).
  - The Freebox API defines 27 known C(host_type) values (source of truth is
    the firmware — the list may evolve). Common values include C(workstation),
    C(laptop), C(smartphone), C(tablet), C(printer), C(nas),
    C(networking_device), C(television), C(multimedia_device),
    C(freebox_delta), and C(other).
options:
  mac:
    description:
      - MAC address of the host to update. Accepts colon or dash separators;
        canonicalised to lowercase colon form internally.
    type: str
    required: true
  primary_name:
    description:
      - Display name for the host shown in the Freebox UI and returned by DNS/mDNS.
    type: str
  host_type:
    description:
      - Classification of the host. The Freebox validates the value server-side;
        pass one of the 27 known values listed in the module description.
    type: str
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Name a newly provisioned VM
  mipsou.freebox.lan_host:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac: "DE:AD:BE:EF:00:01"
    primary_name: fbx-vm-01
    host_type: workstation

- name: Correct the type of a mis-classified device
  mipsou.freebox.lan_host:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac: "AA:BB:CC:DD:EE:FF"
    host_type: nas
"""

RETURN = r"""
host:
  description: Full LAN host dict returned by the Freebox API after the update,
    or the current state when no change was needed.
  returned: always
  type: dict
  sample:
    id: "ether-de:ad:be:ef:00:01"
    primary_name: fbx-vm-01
    host_type: workstation
    reachable: true
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
    as_list,
    validate_mac,
)


def _find_host_by_mac(client, mac):
    """Return ``(host_dict, freebox_id)`` for the LAN host matching ``mac``.

    ``mac`` must already be canonicalised (lowercase colon form).
    The ``l2ident`` field can be a list or a single object — ``as_list`` normalises
    the firmware quirk. Returns ``(None, None)`` when not found.
    """
    hosts = client.get("/lan/browser/pub/") or []
    for host in hosts:
        for ident in as_list(host.get("l2ident")):
            candidate = (ident.get("id") or "").lower().replace("-", ":")
            if candidate == mac:
                return host, host["id"]
    return None, None


def _update_host(module, client, host, host_id, desired):
    """Diff ``desired`` against ``host`` and PUT only the changed keys.

    Returns the result dict (changed, host).
    """
    changed_keys = [k for k, v in desired.items() if host.get(k) != v]
    if not changed_keys:
        return dict(changed=False, host=host)

    simulated = dict(host)
    simulated.update(desired)
    if module.check_mode:
        return dict(changed=True, host=simulated)

    put_body = {k: desired[k] for k in changed_keys}
    updated = client.put("/lan/browser/pub/{0}".format(host_id), body=put_body) or simulated
    return dict(changed=True, host=updated)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        mac=dict(type="str", required=True),
        primary_name=dict(type="str"),
        host_type=dict(type="str"),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
    )

    try:
        mac = validate_mac(module.params["mac"])
    except ValueError as exc:
        module.fail_json(msg="invalid mac: %s" % exc)

    desired = {}
    if module.params.get("primary_name") is not None:
        desired["primary_name"] = module.params["primary_name"]
    if module.params.get("host_type") is not None:
        desired["host_type"] = module.params["host_type"]

    client = FreeboxClient(module)

    try:
        host, host_id = _find_host_by_mac(client, mac)
        if host is None:
            module.fail_json(
                msg="no LAN host found with MAC %s — is the device visible on the network?" % mac
            )
        result = _update_host(module, client, host, host_id, desired)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
