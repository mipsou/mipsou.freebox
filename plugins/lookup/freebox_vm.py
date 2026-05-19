# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
name: freebox_vm
short_description: Look up Freebox VMs by name
description:
  - Queries C(GET /vm/) and returns a list of VM dicts whose C(name) matches
    the given term. Case-sensitive.
  - Returns an empty list if no VM matches (does not raise an error).
version_added: "0.3.0"
author:
  - Mipsou (@mipsou)
options:
  _terms:
    description: VM name(s) to look up.
    required: true
  url:
    description: Freebox base URL.
    type: str
    default: http://mafreebox.freebox.fr
  app_id:
    description: Application identifier.
    type: str
    required: true
  app_token:
    description: Application token.
    type: str
    required: true
    no_log: true
  api_base:
    description: API path prefix.
    type: str
    default: /api/v15
  validate_certs:
    description: Whether to validate TLS certificates.
    type: bool
    default: true
  timeout:
    description: HTTP timeout in seconds.
    type: int
    default: 30
"""

EXAMPLES = r"""
- name: Get VM details
  ansible.builtin.debug:
    msg: "{{ lookup('mipsou.freebox.freebox_vm', 'fbx-vm-01',
              url='http://mafreebox.freebox.fr',
              app_id='ansible',
              app_token=freebox_app_token) }}"
"""

RETURN = r"""
_list:
  description: List of VM dicts matching the requested name.
  type: list
"""

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    FreeboxClient,
    FreeboxError,
)


class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):
        url = kwargs.get("url", "http://mafreebox.freebox.fr")
        app_id = kwargs.get("app_id")
        app_token = kwargs.get("app_token")
        api_base = kwargs.get("api_base", "/api/v15")
        validate_certs = kwargs.get("validate_certs", True)
        timeout = kwargs.get("timeout", 30)

        if not app_id:
            raise AnsibleError("freebox_vm lookup requires 'app_id'")
        if not app_token:
            raise AnsibleError("freebox_vm lookup requires 'app_token'")

        client = FreeboxClient(
            module=None,
            url=url,
            app_id=app_id,
            app_token=app_token,
            api_base=api_base,
            timeout=timeout,
            validate_certs=validate_certs,
        )

        try:
            all_vms = client.get("/vm/") or []
        except FreeboxError as exc:
            raise AnsibleError("freebox_vm lookup error: %s" % exc)

        result = []
        for term in terms:
            matched = [vm for vm in all_vms if vm.get("name") == term]
            result.extend(matched)
        return result
