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
module: dhcp_static_lease
short_description: Manage Freebox DHCP static leases declaratively
version_added: "0.2.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Create, update or delete DHCP static lease reservations on a Freebox.
  - Idempotency is keyed on the MAC address. The Freebox API does not expose
    a PUT on individual leases, so an update is implemented as DELETE+POST.
options:
  mac:
    description:
      - MAC address of the host receiving the static lease. Accepts colon or
        dash separators; canonicalised to lowercase colon form internally.
    type: str
    required: true
  ip:
    description:
      - Reserved IPv4 address. Must be in RFC1918 private space and not end
        in C(.0), C(.1), C(.254) or C(.255) (Freebox-reserved).
      - Required when I(state=present); ignored when I(state=absent).
    type: str
  hostname:
    description:
      - Hostname displayed in the Freebox UI for this reservation.
    type: str
  comment:
    description:
      - Free-form comment shown in the Freebox UI.
    type: str
  state:
    description:
      - C(present) — the reservation must exist and match the requested IP /
        hostname / comment. Update is DELETE+POST since the API does not
        expose a PUT.
      - C(absent) — the reservation must not exist.
    type: str
    choices: [present, absent]
    default: present
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Reserve an IP for the NAS
  mipsou.freebox.dhcp_static_lease:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac: "DE:AD:BE:EF:00:01"
    ip: 192.168.1.20
    hostname: nas-prod
    comment: "Managed by Ansible"

- name: Remove a stale reservation
  mipsou.freebox.dhcp_static_lease:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac: "DE:AD:BE:EF:00:99"
    state: absent
"""

RETURN = r"""
lease:
  description:
    - Final state of the lease (the dict returned by the Freebox API), or the
      previous state when I(state=absent). Empty when no lease existed and
      I(state=absent).
  type: dict
  returned: always
  sample:
    id: "DE:AD:BE:EF:00:01"
    mac: "de:ad:be:ef:00:01"
    ip: "192.168.1.20"
    hostname: "nas-prod"
    comment: "Managed by Ansible"
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
    validate_mac,
)


def _find_lease_by_mac(client, mac):
    """Return the existing lease dict for ``mac``, or ``None`` if absent."""
    leases = client.get("/dhcp/static_lease/") or []
    for lease in leases:
        if (lease.get("mac") or "").lower() == mac:
            return lease
    return None


def _matches_desired(lease, desired):
    """Return True iff every key of ``desired`` matches ``lease``."""
    for key, value in desired.items():
        if value is None:
            continue
        if (lease.get(key) or "") != value:
            return False
    return True


def _ensure_present(module, client, mac, desired):
    existing = _find_lease_by_mac(client, mac)
    if existing is not None and _matches_desired(existing, desired):
        return dict(changed=False, lease=existing)

    if module.check_mode:
        simulated = dict(existing or {})
        simulated.update({k: v for k, v in desired.items() if v is not None})
        simulated["mac"] = mac
        return dict(changed=True, lease=simulated)

    if existing is not None:
        # No PUT on /dhcp/static_lease/{id} — DELETE+POST to update.
        client.delete("/dhcp/static_lease/{0}".format(existing["id"]))

    body = {"mac": mac}
    body.update({k: v for k, v in desired.items() if v is not None})
    created = client.post("/dhcp/static_lease/", body=body) or body
    return dict(changed=True, lease=created)


def _ensure_absent(module, client, mac):
    existing = _find_lease_by_mac(client, mac)
    if existing is None:
        return dict(changed=False, lease={})
    if module.check_mode:
        return dict(changed=True, lease=existing)
    client.delete("/dhcp/static_lease/{0}".format(existing["id"]))
    return dict(changed=True, lease=existing)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        mac=dict(type="str", required=True),
        ip=dict(type="str"),
        hostname=dict(type="str"),
        comment=dict(type="str"),
        state=dict(type="str", default="present", choices=["present", "absent"]),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
        required_if=[("state", "present", ["ip"])],
    )

    try:
        mac = validate_mac(module.params["mac"])
    except ValueError as exc:
        module.fail_json(msg="invalid mac: %s" % exc)

    ip = module.params.get("ip")
    if ip is not None:
        try:
            ip = validate_dhcp_ip(ip)
        except ValueError as exc:
            module.fail_json(msg="invalid ip: %s" % exc)

    client = FreeboxClient(module)
    state = module.params["state"]

    try:
        if state == "absent":
            result = _ensure_absent(module, client, mac)
        else:
            desired = dict(
                ip=ip,
                hostname=module.params.get("hostname"),
                comment=module.params.get("comment"),
            )
            result = _ensure_present(module, client, mac, desired)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
