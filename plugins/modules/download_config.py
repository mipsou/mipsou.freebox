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
module: download_config
short_description: Manage the Freebox global download configuration
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the singleton download configuration at C(/downloads/config/).
  - Path fields (C(download_dir), C(watch_dir)) are provided as cleartext absolute
    paths; the module encodes them to base64 before sending to the API.
  - Only parameters explicitly set are sent to the API; unspecified parameters
    keep their current Freebox-side value.
options:
  download_dir:
    description:
      - Absolute path on the Freebox NAS where downloads are saved.
        The API stores this as base64; supply the cleartext path here.
    type: str
  max_downloading_tasks:
    description:
      - Maximum number of simultaneous active download tasks.
    type: int
  throttling_mode:
    description:
      - Download bandwidth policy.
    type: str
    choices: [normal, slow, hibernate, schedule]
  use_watch_dir:
    description:
      - Whether to monitor a watch directory for new torrent files.
    type: bool
  watch_dir:
    description:
      - Absolute path on the Freebox NAS for the torrent watch directory.
        The API stores this as base64; supply the cleartext path here.
    type: str
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Set download directory
  mipsou.freebox.download_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    download_dir: /Disque dur/Telechargements

- name: Enable throttle and set watch dir
  mipsou.freebox.download_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    throttling_mode: slow
    use_watch_dir: true
    watch_dir: /Disque dur/Torrents
"""

RETURN = r"""
config:
  description: The full download configuration after the call.
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
    encode_path,
    sanitize_path,
)


_PATH_FIELDS = ("download_dir", "watch_dir")
_SCALAR_KEYS = ("max_downloading_tasks", "throttling_mode", "use_watch_dir")


def _compute_diff(before, after, keys):
    return {k: (before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)}


def _update_config(client, desired, check_mode=False):
    """Read-modify-write /downloads/config/. Returns (changed, before, after)."""
    if desired:
        return client.diff_and_put("/downloads/config/", desired, full_body=False, check_mode=check_mode)
    cfg = client.get("/downloads/config/") or {}
    return False, cfg, cfg


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        download_dir=dict(type="str"),
        max_downloading_tasks=dict(type="int"),
        throttling_mode=dict(type="str", choices=["normal", "slow", "hibernate", "schedule"]),
        use_watch_dir=dict(type="bool"),
        watch_dir=dict(type="str"),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    desired = {}
    for key in _SCALAR_KEYS:
        val = module.params.get(key)
        if val is not None:
            desired[key] = val

    for key in _PATH_FIELDS:
        raw = module.params.get(key)
        if raw is not None:
            try:
                clean = sanitize_path(raw)
            except ValueError as exc:
                module.fail_json(msg="invalid %s: %s" % (key, exc))
            desired[key] = encode_path(clean)

    client = FreeboxClient(module)
    try:
        changed, before, after = _update_config(client, desired, module.check_mode)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    diff = _compute_diff(before, after, desired.keys())
    module.exit_json(changed=changed, config=after, diff=diff)


if __name__ == "__main__":
    main()
