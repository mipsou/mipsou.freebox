# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import absolute_import, division, print_function, unicode_literals

__metaclass__ = type


class ModuleDocFragment(object):
    DOCUMENTATION = r"""
options:
  url:
    description:
      - Base URL of the Freebox HTTP API endpoint.
      - For local LAN use, C(http://mafreebox.freebox.fr) is the standard
        hostname. For remote access via the box's public alias, use the
        C(https://<id>.fbxos.fr) form and pair I(validate_certs=false) since
        the box presents a Freebox-internal CA.
    type: str
    default: http://mafreebox.freebox.fr
  app_id:
    description:
      - Application identifier registered with the Freebox during pairing.
        Must match exactly the C(app_id) used at pairing time — the Freebox
        looks up the C(app_token) by this string.
    type: str
    required: true
  app_token:
    description:
      - Long-lived application token obtained from the one-shot pairing flow.
      - Treat as a secret. The modules mark this argument C(no_log=True) so
        it never appears in playbook output or fact dumps.
      - See the C(scripts/pair.py) helper shipped with this collection for
        the pairing flow.
    type: str
    required: true
  api_base:
    description:
      - API version prefix appended to I(url). The collection targets v15 by
        default; override for older firmware.
    type: str
    default: /api/v15
  timeout:
    description:
      - HTTP request timeout in seconds.
    type: int
    default: 30
  validate_certs:
    description:
      - Whether to verify the TLS certificate presented by the Freebox. The
        public C(.fbxos.fr) URL uses a Freebox-internal CA that the
        controller typically does not trust — set to C(false) in that case.
    type: bool
    default: true
"""
