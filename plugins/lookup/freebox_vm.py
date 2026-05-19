# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
name: freebox_vm
short_description: Look up Freebox VM definitions
version_added: "0.3.0"
author:
  - Mipsou (@mipsou)
description:
  - Returns the list of VMs from C(GET /vm/) on the Freebox API.
  - When one or more VM names are passed as terms, only matching VMs are
    returned (exact name match, case-sensitive).
  - Returns a list of dicts with keys C(id), C(name), C(status),
    C(disk_path), C(mac), C(memory), C(vcpus).
options:
  _terms:
    description:
      - Optional VM names to filter by. Return all VMs when omitted.
    type: list
    elements: str
  url:
    description:
      - Freebox API base URL.
    type: str
    default: http://mafreebox.freebox.fr
  app_id:
    description:
      - Application identifier registered with the Freebox.
    type: str
    required: true
  app_token:
    description:
      - Application token (secret).
    type: str
    required: true
    secret: true
  api_base:
    description:
      - API path prefix.
    type: str
    default: /api/v15
  validate_certs:
    description:
      - Whether to verify TLS certificates.
    type: bool
    default: true
"""

EXAMPLES = r"""
# Return all VMs
- name: List all Freebox VMs
  ansible.builtin.debug:
    msg: "{{ lookup('mipsou.freebox.freebox_vm',
               url='http://mafreebox.freebox.fr',
               app_id='ansible',
               app_token=freebox_app_token) }}"

# Filter by name
- name: Get info for fbx-vm-01
  ansible.builtin.debug:
    msg: "{{ lookup('mipsou.freebox.freebox_vm', 'fbx-vm-01',
               url='http://mafreebox.freebox.fr',
               app_id='ansible',
               app_token=freebox_app_token) }}"
"""

RETURN = r"""
_list:
  description: List of VM dicts matching the optional name filter.
  type: list
  elements: dict
  contains:
    id:
      description: Numeric VM identifier.
      type: int
    name:
      description: VM display name.
      type: str
    status:
      description: Current VM state (e.g. C(running), C(stopped)).
      type: str
    disk_path:
      description: Path to the primary disk image (base64-decoded).
      type: str
    mac:
      description: VM MAC address.
      type: str
    memory:
      description: Allocated RAM in MiB.
      type: int
    vcpus:
      description: Number of virtual CPUs.
      type: int
"""

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    FreeboxClient,
    FreeboxError,
    decode_path,
)

_VM_FIELDS = ("id", "name", "status", "mac", "memory", "vcpus")


def _normalise_vm(vm):
    """Return a normalized VM dict with decode_path applied to disk_path."""
    result = {f: vm.get(f) for f in _VM_FIELDS}
    raw_disk = vm.get("disk_path", "")
    if raw_disk:
        try:
            result["disk_path"] = decode_path(raw_disk)
        except FreeboxError:
            result["disk_path"] = raw_disk
    else:
        result["disk_path"] = ""
    return result


def _filter_by_names(vms, terms):
    """Return vms matching any of the names in terms (or all if terms is empty)."""
    if not terms:
        return vms
    names = set(terms)
    return [vm for vm in vms if vm.get("name") in names]


class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):
        self.set_options(var_options=variables, direct=kwargs)

        url = kwargs.get("url", "http://mafreebox.freebox.fr")
        app_id = kwargs.get("app_id")
        app_token = kwargs.get("app_token")
        api_base = kwargs.get("api_base", "/api/v15")
        validate_certs = kwargs.get("validate_certs", True)

        if not app_id or not app_token:
            raise AnsibleError("freebox_vm lookup requires app_id and app_token")

        client = FreeboxClient(
            module=None,
            url=url,
            app_id=app_id,
            app_token=app_token,
            api_base=api_base,
            validate_certs=validate_certs,
        )

        try:
            vms = client.get("/vm/") or []
        except FreeboxError as exc:
            raise AnsibleError("freebox_vm: %s" % exc)

        normalised = [_normalise_vm(vm) for vm in vms]

        normalised = _filter_by_names(normalised, terms)

        return normalised
