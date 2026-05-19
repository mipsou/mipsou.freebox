"""Make collection plugins importable in standalone pytest runs.

When tests are launched via ``ansible-test units --venv`` (the canonical
harness), the collection is on the Ansible collections path and import works
as ``ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api``.

For developer-driven runs with plain pytest — including Windows hosts where
``ansible.module_utils.basic`` is unimportable (it pulls in the Unix-only
``grp`` module) — this conftest installs stub Ansible modules sufficient for
the pure-Python helpers in ``module_utils.freebox_api``. The HTTP layer is
monkey-patched by individual tests, so the stubs need only expose the right
names.
"""
import importlib
import os
import sys
import types

try:
    from urllib.parse import quote as _stdlib_quote  # Python 3
except ImportError:  # pragma: no cover — py2 fallback for ansible-test legacy.ini runs
    from urllib import quote as _stdlib_quote


COLLECTION_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if COLLECTION_ROOT not in sys.path:
    sys.path.insert(0, COLLECTION_ROOT)


def _install_ansible_stubs():
    """Install minimal stubs for ``ansible.module_utils.*`` if the real
    package is unavailable on this platform (notably Windows)."""
    try:
        import ansible.module_utils.urls  # noqa: F401
        import ansible.module_utils.basic  # noqa: F401
        import ansible.module_utils.six.moves.urllib.parse  # noqa: F401
        return
    except ImportError:
        pass

    ansible = sys.modules.setdefault("ansible", types.ModuleType("ansible"))
    mu = sys.modules.setdefault("ansible.module_utils", types.ModuleType("ansible.module_utils"))
    ansible.module_utils = mu

    urls = types.ModuleType("ansible.module_utils.urls")

    def _stub_fetch_url(*args, **kwargs):
        raise RuntimeError(
            "fetch_url stub was not patched; tests must monkeypatch "
            "freebox_api.fetch_url before triggering HTTP calls"
        )

    def _stub_open_url(*args, **kwargs):
        raise RuntimeError(
            "open_url stub was not patched; tests must monkeypatch "
            "freebox_api.open_url before triggering HTTP calls"
        )

    urls.fetch_url = _stub_fetch_url
    urls.open_url = _stub_open_url
    sys.modules["ansible.module_utils.urls"] = urls
    mu.urls = urls

    basic = types.ModuleType("ansible.module_utils.basic")

    class _StubAnsibleModule(object):
        def __init__(self, *a, **kw):
            self.params = {}

        def fail_json(self, **kw):
            raise SystemExit(kw)

        def exit_json(self, **kw):
            raise SystemExit(kw)

        def warn(self, msg):
            pass

    basic.AnsibleModule = _StubAnsibleModule
    sys.modules["ansible.module_utils.basic"] = basic
    mu.basic = basic

    six = types.ModuleType("ansible.module_utils.six")
    moves = types.ModuleType("ansible.module_utils.six.moves")
    urllib_pkg = types.ModuleType("ansible.module_utils.six.moves.urllib")
    parse_mod = types.ModuleType("ansible.module_utils.six.moves.urllib.parse")
    parse_mod.quote = _stdlib_quote
    sys.modules["ansible.module_utils.six"] = six
    sys.modules["ansible.module_utils.six.moves"] = moves
    sys.modules["ansible.module_utils.six.moves.urllib"] = urllib_pkg
    sys.modules["ansible.module_utils.six.moves.urllib.parse"] = parse_mod
    mu.six = six
    six.moves = moves
    moves.urllib = urllib_pkg
    urllib_pkg.parse = parse_mod


def _install_collection_alias():
    """Map ``ansible_collections.mipsou.freebox`` → local ``plugins`` package."""
    qualified = "ansible_collections.mipsou.freebox"
    if qualified in sys.modules:
        return
    try:
        import ansible_collections  # noqa: F401
    except ImportError:
        ansible_collections = types.ModuleType("ansible_collections")
        sys.modules["ansible_collections"] = ansible_collections
    try:
        mipsou_ns = importlib.import_module("ansible_collections.mipsou")
    except ImportError:
        mipsou_ns = types.ModuleType("ansible_collections.mipsou")
        sys.modules["ansible_collections.mipsou"] = mipsou_ns
        sys.modules["ansible_collections"].community = mipsou_ns

    pkg = types.ModuleType(qualified)
    pkg.__path__ = [COLLECTION_ROOT]
    sys.modules[qualified] = pkg
    mipsou_ns.freebox = pkg

    plugins_pkg = types.ModuleType(qualified + ".plugins")
    plugins_pkg.__path__ = [os.path.join(COLLECTION_ROOT, "plugins")]
    sys.modules[qualified + ".plugins"] = plugins_pkg
    pkg.plugins = plugins_pkg

    mu_pkg = types.ModuleType(qualified + ".plugins.module_utils")
    mu_pkg.__path__ = [os.path.join(COLLECTION_ROOT, "plugins", "module_utils")]
    sys.modules[qualified + ".plugins.module_utils"] = mu_pkg
    plugins_pkg.module_utils = mu_pkg


_install_ansible_stubs()
_install_collection_alias()
