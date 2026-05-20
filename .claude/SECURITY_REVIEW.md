# Security Review — Action Required Before Wave 3

4 blocking fixes identified by the supervisor session. Apply these first, with tests.

## Fix 1 — CRITICAL: `cloudinit_userdata` missing `no_log=True` (vm.py:503)

Cloud-init often contains passwords, SSH keys, vault tokens — appears in plain text
in Ansible logs without this flag.

```python
# plugins/modules/vm.py — in argspec:
cloudinit_userdata=dict(type="str", no_log=True),
```

Add a unit test that asserts `no_log` is set on this argument.

## Fix 2 — CRITICAL: `disk.name` not using `validate_disk_name()` (vm.py:337)

The current check only rejects `/` and `\\`. `validate_disk_name()` already exists
in `freebox_api.py` and additionally rejects `..`, enforces `.qcow2`/`.raw` extension.
It is not being called in `_validate_disk_spec`.

```python
# plugins/modules/vm.py — _validate_disk_spec():
from ...freebox_api import ..., validate_disk_name

try:
    name = validate_disk_name(disk["name"])
except ValueError as exc:
    module.fail_json(msg="invalid disk.name: %s" % exc)
return source_image, dst_dir, name
```

## Fix 3 — HIGH: `src_ip` not validated in port_forward.py (port_forward.py:264)

`src_ip` is passed raw to the Freebox API. If non-empty, validate the host part
as a valid IPv4 (use `_parse_ipv4` from `freebox_api.py`).

```python
src_ip = module.params.get("src_ip") or ""
if src_ip:
    host = src_ip.split("/")[0]
    try:
        _parse_ipv4(host)
    except ValueError as exc:
        module.fail_json(msg="invalid src_ip: %s" % exc)
```

Note: `_parse_ipv4` is a module-private function — either expose it or inline the
validation. Exposing it (remove the leading `_`) is cleaner.

## Fix 4 — HIGH: `decode_path` unprotected (freebox_api.py:70)

A malformed `disk_path` returned by the API raises bare `binascii.Error` instead
of a `FreeboxError`. Wrap it:

```python
def decode_path(encoded):
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise FreeboxError("cannot decode path %r: %s" % (encoded, exc))
```

## Additional notes (non-blocking, can follow in same PR)

- `freebox_api.py:305` — Add comment: `# SHA-1 is Freebox-API-mandated (HMAC challenge)`
- `freebox_api.py:191` — `sanitize_path` should reject null bytes: `if "\x00" in path: raise ValueError(...)`
- `port_forward.py:239` — Clarify the `wan_end` assignment logic (confusing intermediate `None`)

## Wave 3 direction (after fixes are committed)

Order: **route** → **wifi_ssid** → **system**

- `route.py` — static IPv4/IPv6 routes, same structure as `dhcp_static_lease`
- `wifi_ssid.py` — enabled/disabled per SSID
- `system.py` — facts + reboot

Info/read-only modules (storage, vpn, switch, etc.) as a separate dedicated wave after.
