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
module: wifi_ssid
short_description: Manage Freebox Wi-Fi SSID settings declaratively
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Update settings of an existing Wi-Fi SSID on a Freebox.
  - Idempotency is keyed on the SSID name. Fails if no SSID with that
    name is found; creation of new SSIDs is out of scope.
  - If multiple SSIDs share the same name (different bands), use
    I(ap_id) to select the specific access point.
  - Only C(state=present) is supported; use I(enabled=false) to disable
    without removing.
options:
  name:
    description: SSID name to manage.
    type: str
    required: true
  ap_id:
    description:
      - Access-point ID to restrict the match when multiple APs broadcast
        the same SSID name. Omit to match the first SSID with I(name).
    type: int
  enabled:
    description: Whether the SSID should be broadcasting.
    type: bool
  hide_ssid:
    description: Whether to hide the SSID (suppress beacon broadcast).
    type: bool
  encryption:
    description: Encryption mode (e.g. C(wpa2_ccmp), C(wpa_auto_ccmp)).
    type: str
  state:
    description:
      - Only C(present) is supported; the SSID must already exist on the
        Freebox. Use I(enabled=false) to suppress it without deleting.
    type: str
    choices: [present]
    default: present
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Enable the main Wi-Fi SSID
  mipsou.freebox.wifi_ssid:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    name: MyNetwork
    enabled: true

- name: Hide the guest SSID
  mipsou.freebox.wifi_ssid:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    name: GuestNetwork
    hide_ssid: true

- name: Disable the 5 GHz SSID on AP 1
  mipsou.freebox.wifi_ssid:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    name: MyNetwork
    ap_id: 1
    enabled: false
"""

RETURN = r"""
ssid:
  description: Final state of the SSID dict.
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
)


_SETTABLE_FIELDS = ("enabled", "hide_ssid", "encryption")


def _find_ssid(client, name, ap_id=None):
    """Return the first SSID dict matching name (and optionally ap_id)."""
    ssids = client.get("/wifi/bss/") or []
    for ssid in ssids:
        if ssid.get("ssid") == name:
            if ap_id is None or ssid.get("ap_id") == ap_id:
                return ssid
    return None


def _diff_fields(existing, desired):
    return {k: v for k, v in desired.items() if v is not None and existing.get(k) != v}


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        name=dict(type="str", required=True),
        ap_id=dict(type="int"),
        enabled=dict(type="bool"),
        hide_ssid=dict(type="bool"),
        encryption=dict(type="str"),
        state=dict(type="str", default="present", choices=["present"]),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
    )

    name = module.params["name"]
    ap_id = module.params.get("ap_id")

    desired = {
        k: module.params[k]
        for k in _SETTABLE_FIELDS
        if module.params.get(k) is not None
    }

    client = FreeboxClient(module)
    try:
        existing = _find_ssid(client, name, ap_id)
        if existing is None:
            ap_msg = " on ap_id=%d" % ap_id if ap_id is not None else ""
            module.fail_json(msg="SSID %r not found%s" % (name, ap_msg))

        diff = _diff_fields(existing, desired)
        if not diff:
            module.exit_json(changed=False, ssid=existing)

        if module.check_mode:
            simulated = dict(existing)
            simulated.update(diff)
            module.exit_json(changed=True, ssid=simulated)

        ssid_id = existing["id"]
        ap_id_actual = existing["ap_id"]
        updated = client.put(
            "/wifi/ap/{0}/ssid/{1}".format(ap_id_actual, ssid_id),
            body=diff,
        ) or dict(existing, **diff)
        module.exit_json(changed=True, ssid=updated)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))


if __name__ == "__main__":
    main()
