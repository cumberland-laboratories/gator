"""B1 Slice 1 unit tests — safe content transport helpers.

Covers the helpers introduced in `gator-dashboard.py` and
`dashboard/content_policy.py` per the B1 execution errata + r6 plan:

- `parse_logical_path` (§10.1)
- `_is_reserved_windows_component` + `_WIN_RESERVED_STEMS_EXPLICIT`
  (§10.10 including errata E5 trailing-space normalization)
- `_parse_request` (§10.7 including errata E2 all-slash + E3 parse_qs
  route-aware ParseError)
- `_serialize_listing_entry` (E1 wire schema for all three namespaces
  plus ValueError on unknown namespace)
- `_raw_error_direct` (§10.6 F3 concrete self-contained raw responder)
- `_dispatch_parse_error` (§10.6 F2 route-aware pre-dispatch)

HTTP integration pins (Slice 2 + 3) live in a separate module and hit
the actual subprocess dashboard. Slice 1 focuses on unit tests that
exercise the pure helpers via the `dashboard_module` fixture from
Plan A.
"""

import io
import re
import sys
import types

import pytest


# ── logical-path parser ──────────────────────────────────────────

def test_logical_path_source_namespace(dashboard_module):
    lp = dashboard_module.parse_logical_path("source/example.py")
    assert lp is not None
    assert lp.namespace_root == ""
    assert lp.disk_rel == "example.py"
    assert lp.git_rel == "example.py"


def test_logical_path_gator_command_namespace(dashboard_module):
    lp = dashboard_module.parse_logical_path(
        "gator-command/README.md")
    assert lp is not None
    assert lp.namespace_root == "gator-command"
    assert lp.disk_rel == "README.md"
    assert lp.git_rel == "gator-command/README.md"


def test_logical_path_implicit_dotgator_namespace(dashboard_module):
    lp = dashboard_module.parse_logical_path("mission.md")
    assert lp is not None
    assert lp.namespace_root == ".gator"
    assert lp.disk_rel == "mission.md"
    assert lp.git_rel == ".gator/mission.md"


def test_logical_path_rejects_explicit_dotgator_prefix(
        dashboard_module):
    assert dashboard_module.parse_logical_path(
        ".gator/mission.md") is None


def test_logical_path_rejects_case_aliases(dashboard_module):
    for logical in ("Source/x.py", ".GATOR/mission.md",
                    "Gator-Command/README.md",
                    ".Gator/mission.md"):
        assert dashboard_module.parse_logical_path(logical) is None, (
            f"expected reject for {logical!r}")


def test_logical_path_rejects_traversal(dashboard_module):
    assert dashboard_module.parse_logical_path(
        "source/../etc/passwd") is None


def test_logical_path_rejects_backslash(dashboard_module):
    assert dashboard_module.parse_logical_path(
        "source/foo\\bar.py") is None


def test_logical_path_rejects_control_char(dashboard_module):
    assert dashboard_module.parse_logical_path(
        "source/foo\x07bar.py") is None


def test_logical_path_rejects_tilde_prefix(dashboard_module):
    assert dashboard_module.parse_logical_path("~/etc/passwd") is None


def test_logical_path_rejects_empty(dashboard_module):
    for value in ("", None, "source/"):
        assert dashboard_module.parse_logical_path(value) is None


def test_logical_path_rejects_drive_relative(dashboard_module):
    assert dashboard_module.parse_logical_path(
        "source/C:secret.txt") is None


def test_logical_path_rejects_ads_colon(dashboard_module):
    assert dashboard_module.parse_logical_path(
        "source/private.pem:leak.md") is None


def test_logical_path_rejects_trailing_dot(dashboard_module):
    assert dashboard_module.parse_logical_path(
        "sessions/_active./token.json") is None


def test_logical_path_rejects_dos_devices(dashboard_module):
    for shape in ("source/CON.txt", "source/NUL.md",
                  "source/LPT1", "source/COM9.log"):
        assert dashboard_module.parse_logical_path(shape) is None, (
            f"expected DOS-device reject for {shape!r}")


def test_logical_path_positive_returns_triple_type(
        dashboard_module):
    lp = dashboard_module.parse_logical_path("source/x.py")
    # Namedtuple contract — indexed AND attribute access agree.
    assert lp[0] == lp.namespace_root == ""
    assert lp[1] == lp.disk_rel == "x.py"
    assert lp[2] == lp.git_rel == "x.py"


# ── Windows reserved name (E5 trailing-space, r6 durability) ────

def test_reserved_windows_covers_basic_stems(dashboard_module):
    for name in ("CON", "PRN", "AUX", "NUL",
                 "con", "nul.txt", "aux.log", "prn.md"):
        assert dashboard_module._is_reserved_windows_component(name), (
            f"expected reserved: {name!r}")


def test_reserved_windows_covers_com_lpt_ascii_digits(
        dashboard_module):
    for name in ("COM1", "COM9", "LPT1", "LPT9",
                 "com1.txt", "LPT9.md"):
        assert dashboard_module._is_reserved_windows_component(name), (
            f"expected reserved: {name!r}")


def test_reserved_windows_covers_superscript_com(dashboard_module):
    for name in ("COM¹", "COM²", "COM³",
                 "com¹.txt", "COM³.md"):
        assert dashboard_module._is_reserved_windows_component(name), (
            f"expected superscript reserved: {name!r}")


def test_reserved_windows_covers_superscript_lpt(dashboard_module):
    for name in ("LPT¹", "LPT²", "LPT³",
                 "lpt¹.log"):
        assert dashboard_module._is_reserved_windows_component(name), (
            f"expected superscript reserved: {name!r}")


def test_reserved_windows_covers_console_devices(dashboard_module):
    for name in ("CONIN$", "CONOUT$", "CONIN$.txt", "conout$.md"):
        assert dashboard_module._is_reserved_windows_component(name), (
            f"expected console-device reserved: {name!r}")


def test_reserved_windows_normal_names_pass(dashboard_module):
    for name in ("example.py", "README.md", "mission.md",
                 "config.json", "com.txt", "lpt.py",
                 "CONTRIBUTING.md"):
        assert not dashboard_module._is_reserved_windows_component(
            name), f"expected NOT reserved: {name!r}"


def test_reserved_windows_e5_trailing_space_forms(dashboard_module):
    """E5 — trailing spaces before the extension must not defeat
    layer 1 (the explicit set). Simulate stdlib layer 2 being
    unavailable so we prove the explicit check alone catches them.
    """
    from unittest.mock import patch

    # Neutralize the stdlib probe so only layer 1 answers.
    def _boom(self):
        raise AttributeError(
            "PureWindowsPath.is_reserved simulated-removed")

    with patch.object(dashboard_module.PureWindowsPath,
                      "is_reserved", _boom):
        for name in ("NUL .txt", "COM1 .md", "CONIN$ .txt",
                     "NUL\t.txt"):
            assert dashboard_module._is_reserved_windows_component(
                name), f"expected E5 reserved (layer 1 only): {name!r}"


def test_reserved_windows_explicit_set_matches_known_families(
        dashboard_module):
    """Regression stub: every documented family the errata E5 fix
    guarantees is present in the explicit set. If Microsoft
    documents a new family, this fixture must be extended AND
    this test kept in sync — it does not auto-detect stdlib
    changes.
    """
    explicit = dashboard_module._WIN_RESERVED_STEMS_EXPLICIT
    for member in (
        "con", "prn", "aux", "nul",
        "com1", "com5", "com9",
        "lpt1", "lpt5", "lpt9",
        "com¹", "com²", "com³",
        "lpt¹", "lpt²", "lpt³",
        "conin$", "conout$",
    ):
        assert member in explicit, f"missing family: {member!r}"


def test_reserved_windows_stdlib_divergence_is_logged(
        dashboard_module, caplog):
    """r6 durability — when stdlib flags a name the explicit set
    missed, the check returns True AND logs a
    `dashboard.security` warning so the explicit set gets
    updated.
    """
    from unittest.mock import patch

    def _yes(self):
        return True

    with patch.object(dashboard_module.PureWindowsPath,
                      "is_reserved", _yes):
        with caplog.at_level("WARNING", logger="dashboard.security"):
            result = dashboard_module._is_reserved_windows_component(
                "XYZFAKE.txt")
    assert result is True
    assert any(
        "reserved_name_only_in_stdlib" in rec.getMessage()
        for rec in caplog.records)


# ── URL parser (E2 all-slash, E3 parse_qs, route-aware errors) ──

def _fake_handler(path):
    """Build the minimum shim `_parse_request` reads: `handler.path`."""
    h = types.SimpleNamespace()
    h.path = path
    return h


def test_parse_success_basic(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/raw/source/x.py"))
    assert err is None
    assert req.endpoint == "raw"
    assert req.repo_name == "alpha"
    assert req.logical_path == "source/x.py"
    assert req.version_present is False


def test_parse_decodes_repo_name_with_space(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/repo%20alpha/files"))
    assert err is None
    assert req.endpoint == "files"
    assert req.repo_name == "repo alpha"
    assert req.logical_path is None


def test_parse_files_no_logical_path(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/files"))
    assert err is None
    assert req.endpoint == "files"
    assert req.logical_path is None


def test_parse_repo_scope_history_classified_as_other(
        dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/history"))
    assert err is None
    assert req.endpoint == "other"
    assert req.logical_path is None


def test_parse_search_classified_as_other(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/search?q=mission"))
    assert err is None
    assert req.endpoint == "other"


def test_parse_check_classified_as_other(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/check"))
    assert err is None
    assert req.endpoint == "other"


def test_parse_commits_classified_as_other(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/commits"))
    assert err is None
    assert req.endpoint == "other"


def test_parse_repo_root_classified_as_other(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha"))
    assert err is None
    assert req.endpoint == "other"


def test_parse_totally_unrelated_path_is_other(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/dashboard.js"))
    assert err is None
    assert req.endpoint == "other"


def test_parse_files_extra_returns_404(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/files/extra"))
    assert req is None
    assert err.status == 404
    assert err.response_kind == "json"


def test_parse_file_missing_logical_returns_400_json(
        dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/file"))
    assert req is None
    assert err.status == 400
    assert err.response_kind == "json"


def test_parse_raw_missing_logical_returns_400_raw(
        dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/raw"))
    assert req is None
    assert err.status == 400
    assert err.response_kind == "raw"


def test_parse_rejects_encoded_forward_slash(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/raw/source%2fx.py"))
    assert req is None
    assert err.status == 400
    assert "encoded slash" in err.message


def test_parse_rejects_encoded_backslash(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/raw/source/%5c..%5cetc"))
    assert req is None
    assert err.status == 400


def test_parse_rejects_malformed_percent(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/raw/source/x%ZZ.py"))
    assert req is None
    assert err.status == 400
    assert "malformed percent-escape" in err.message


def test_parse_rejects_double_encoded_percent_two_f(
        dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/raw/source/%252fx.py"))
    assert req is None
    assert err.status == 400
    assert "double-encoded" in err.message


def test_parse_decodes_once_no_extra_pass(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler(
            "/api/repo/alpha/raw/source/hello%20world.py"))
    assert err is None
    assert req.logical_path == "source/hello world.py"


def test_parse_utf8_invalid_error_string(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/raw/source/x%FF.py"))
    assert req is None
    assert err.status == 400
    assert err.message == "malformed UTF-8 in URL"  # E4-aligned


# ── E2 all-slash normalization ──────────────────────────────────

def test_e2_repo_scope_history_with_trailing_slash_is_other(
        dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/history/"))
    assert err is None
    assert req.endpoint == "other", (
        "trailing slash on /history must fall through to legacy "
        "repo-history, not be stolen by B1 file-history")


def test_e2_files_with_trailing_slash_is_files(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/files/"))
    assert err is None
    assert req.endpoint == "files"


def test_e2_file_with_trailing_slash_and_logical(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/file/mission.md/"))
    assert err is None
    assert req.endpoint == "file"
    assert req.logical_path == "mission.md"


def test_e2_repeated_trailing_slashes_normalized(dashboard_module):
    """E2 — shipped uses rstrip('/'), not a single-slash strip. Prove
    parity for repeated trailing slashes on all three shapes.
    """
    for suffix in ("/", "//", "///", "////"):
        req_single, _ = dashboard_module._parse_request(
            _fake_handler("/api/repo/alpha/files"))
        req_multi, _ = dashboard_module._parse_request(
            _fake_handler(f"/api/repo/alpha/files{suffix}"))
        assert req_single.endpoint == req_multi.endpoint == "files"

        req_h_s, _ = dashboard_module._parse_request(
            _fake_handler("/api/repo/alpha/history"))
        req_h_m, _ = dashboard_module._parse_request(
            _fake_handler(f"/api/repo/alpha/history{suffix}"))
        assert req_h_s.endpoint == req_h_m.endpoint == "other"

        req_f_s, _ = dashboard_module._parse_request(
            _fake_handler("/api/repo/alpha/file/mission.md"))
        req_f_m, _ = dashboard_module._parse_request(
            _fake_handler(f"/api/repo/alpha/file/mission.md{suffix}"))
        assert req_f_s.endpoint == req_f_m.endpoint == "file"
        assert req_f_s.logical_path == req_f_m.logical_path


# ── E3 parse_qs version-key detection ──────────────────────────

def test_e3_literal_version_key_detected(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler(
            "/api/repo/alpha/raw/source/x.py?version=abc"))
    assert err is None
    assert req.version_present is True
    assert req.version_value == "abc"


def test_e3_percent_encoded_version_key_detected(dashboard_module):
    """E3 — `%76ersion=abc` decodes to `version=abc` under
    parse_qs; the pre-r6 raw regex missed this and would drop
    Cache-Control: no-store. r6 errata fix routes ALL query
    parsing through parse_qs at parser start.
    """
    req, err = dashboard_module._parse_request(
        _fake_handler(
            "/api/repo/alpha/raw/source/x.py?%76ersion=abc"))
    assert err is None
    assert req.version_present is True


def test_e3_percent_encoded_version_on_malformed_path_still_flags(
        dashboard_module):
    """E3 — the version-key detection MUST run even when the path
    itself fails to parse, so version-bearing error responses
    still carry no-store. Malformed percent in path + percent-
    encoded version key.
    """
    req, err = dashboard_module._parse_request(
        _fake_handler(
            "/api/repo/alpha/file/x%ZZ.py?%76ersion=abc"))
    assert req is None
    assert err.status == 400
    assert err.version_present is True
    assert err.response_kind == "json"


def test_e3_no_version_key_flag_false(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler("/api/repo/alpha/raw/source/x.py"))
    assert err is None
    assert req.version_present is False


def test_e3_empty_version_value_still_present(dashboard_module):
    req, err = dashboard_module._parse_request(
        _fake_handler(
            "/api/repo/alpha/raw/source/x.py?version="))
    assert err is None
    assert req.version_present is True
    assert req.version_value == ""


# ── E1 wire-schema serializer ──────────────────────────────────

def test_serializer_source_repo_shape(dashboard_module):
    from dashboard.content_policy import _serialize_listing_entry
    entry = _serialize_listing_entry(
        "", "example.py", "example.py", 42, mtime=1.5)
    assert entry == {
        "path": "source/example.py",
        "name": "example.py",
        "dir": "source",
        "size": 42,
        "source": "repo",
        "mtime": 1.5,
    }


def test_serializer_gator_shape(dashboard_module):
    from dashboard.content_policy import _serialize_listing_entry
    entry = _serialize_listing_entry(
        ".gator", "mission.md", "mission.md", 100)
    assert entry["path"] == "mission.md"
    assert entry["source"] == ".gator"
    assert entry["dir"] == ""
    assert "mtime" not in entry  # optional, absent when not passed


def test_serializer_gator_command_shape(dashboard_module):
    from dashboard.content_policy import _serialize_listing_entry
    entry = _serialize_listing_entry(
        "gator-command", "README.md", "README.md", 200)
    assert entry["path"] == "gator-command/README.md"
    assert entry["source"] == "gator-command"
    assert entry["dir"] == "gator-command"


def test_serializer_nested_source_dir(dashboard_module):
    from dashboard.content_policy import _serialize_listing_entry
    entry = _serialize_listing_entry(
        "", "src/pkg/mod.py", "mod.py", 10)
    assert entry["path"] == "source/src/pkg/mod.py"
    assert entry["dir"] == "source/src/pkg"


def test_serializer_nested_gator_dir(dashboard_module):
    from dashboard.content_policy import _serialize_listing_entry
    entry = _serialize_listing_entry(
        ".gator", "blueprints/sample.svg", "sample.svg", 10)
    assert entry["path"] == "blueprints/sample.svg"
    assert entry["dir"] == "blueprints"


def test_serializer_unknown_namespace_raises_value_error(
        dashboard_module):
    """E1 tightening — the namespace enum is closed; an unknown
    value at the security boundary is a bug, not a fallback. Do
    not silently mislabel.
    """
    from dashboard.content_policy import _serialize_listing_entry
    with pytest.raises(ValueError):
        _serialize_listing_entry(
            "unknown-namespace", "x.md", "x.md", 1)


def test_serializer_content_policy_module_imports(
        dashboard_module):
    """Sanity — content_policy imports cleanly with its
    module-level assertion (every allowlist ext has a MIME).
    """
    from dashboard import content_policy as cp
    assert cp._ALLOWED_TEXT_EXTS_SOURCE
    assert cp._ALLOWED_TEXT_EXTS_GOVERNANCE
    assert cp._ALLOWED_RAW_ASSET_EXTS
    # _text_exts_for symmetry.
    assert cp._text_exts_for(".gator") is (
        cp._ALLOWED_TEXT_EXTS_GOVERNANCE)
    assert cp._text_exts_for("gator-command") is (
        cp._ALLOWED_TEXT_EXTS_GOVERNANCE)
    assert cp._text_exts_for("") is cp._ALLOWED_TEXT_EXTS_SOURCE


# ── _raw_error_direct (F3) via BytesIO shim ─────────────────────

class _FakeHandler:
    """Minimum request-handler shim for `_raw_error_direct`
    unit tests. Records headers in order, captures status calls,
    and gives the body a real BytesIO to write into.
    """

    def __init__(self):
        self.wfile = io.BytesIO()
        self.status_calls = []
        self.headers = []
        self.end_headers_calls = 0

    def send_response(self, status, message=None):
        self.status_calls.append((status, message))

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        self.end_headers_calls += 1


def _bind(dashboard_module, name, shim):
    """Bind an unbound handler method to a shim so it acts as
    `shim.<name>()`.
    """
    method = getattr(dashboard_module.DashboardHandler, name)
    return method.__get__(shim, dashboard_module.DashboardHandler)


def test_raw_error_direct_status_sent_once(dashboard_module):
    shim = _FakeHandler()
    _bind(dashboard_module, "_raw_error_direct", shim)(
        404, "not found", False)
    assert len(shim.status_calls) == 1
    assert shim.status_calls[0][0] == 404
    assert shim.end_headers_calls == 1


def test_raw_error_direct_full_header_sequence_with_version(
        dashboard_module):
    shim = _FakeHandler()
    _bind(dashboard_module, "_raw_error_direct", shim)(
        400, "bad", True)
    names = [n for (n, _) in shim.headers]
    assert names == [
        "Content-Type",
        "Content-Length",
        "X-Content-Type-Options",
        "Cache-Control",
    ]
    values = dict(shim.headers)
    assert values["Content-Type"] == "text/html;charset=utf-8"
    assert values["X-Content-Type-Options"] == "nosniff"
    assert values["Cache-Control"] == "no-store"
    assert int(values["Content-Length"]) == len(shim.wfile.getvalue())


def test_raw_error_direct_no_version_omits_cache_control(
        dashboard_module):
    shim = _FakeHandler()
    _bind(dashboard_module, "_raw_error_direct", shim)(
        500, "boom", False)
    names = [n for (n, _) in shim.headers]
    assert "Cache-Control" not in names
    # nosniff still unconditional.
    assert "X-Content-Type-Options" in names


def test_raw_error_direct_body_bytes_match_template(
        dashboard_module):
    shim = _FakeHandler()
    _bind(dashboard_module, "_raw_error_direct", shim)(
        500, "boom", True)
    body = shim.wfile.getvalue().decode("utf-8")
    assert "500" in body
    assert "boom" in body
    assert body.startswith("<!DOCTYPE html>")


def test_raw_error_direct_html_escapes_message(dashboard_module):
    """The message contains angle brackets — the helper must
    HTML-escape them so the raw body cannot smuggle markup.
    """
    shim = _FakeHandler()
    _bind(dashboard_module, "_raw_error_direct", shim)(
        400, "<script>alert(1)</script>", False)
    body = shim.wfile.getvalue().decode("utf-8")
    assert "&lt;script&gt;" in body
    assert "<script>alert(1)</script>" not in body


# ── _dispatch_parse_error (F2 route-aware) ─────────────────────

class _FakeJsonHandler(_FakeHandler):
    """Records _send_json_error / _raw_error_direct calls without
    running them, so we can prove the dispatch went to the right
    responder.
    """

    def __init__(self):
        super().__init__()
        self.json_error_calls = []
        self.raw_direct_calls = []

    def _send_json_error(self, status, message, *,
                          cache_control=None):
        self.json_error_calls.append(
            (status, message, cache_control))

    def _raw_error_direct(self, status, message, version_present):
        self.raw_direct_calls.append(
            (status, message, version_present))


def test_dispatch_parse_error_json_no_version(dashboard_module):
    shim = _FakeJsonHandler()
    perr = dashboard_module.ParseError(
        status=400, message="bad",
        response_kind="json", version_present=False)
    _bind(dashboard_module, "_dispatch_parse_error", shim)(perr)
    assert shim.json_error_calls == [(400, "bad", None)]
    assert shim.raw_direct_calls == []


def test_dispatch_parse_error_json_with_version(dashboard_module):
    shim = _FakeJsonHandler()
    perr = dashboard_module.ParseError(
        status=400, message="bad",
        response_kind="json", version_present=True)
    _bind(dashboard_module, "_dispatch_parse_error", shim)(perr)
    assert shim.json_error_calls == [(400, "bad", "no-store")]


def test_dispatch_parse_error_raw_no_version(dashboard_module):
    shim = _FakeJsonHandler()
    perr = dashboard_module.ParseError(
        status=400, message="bad",
        response_kind="raw", version_present=False)
    _bind(dashboard_module, "_dispatch_parse_error", shim)(perr)
    assert shim.raw_direct_calls == [(400, "bad", False)]
    assert shim.json_error_calls == []


def test_dispatch_parse_error_raw_with_version(dashboard_module):
    shim = _FakeJsonHandler()
    perr = dashboard_module.ParseError(
        status=400, message="bad",
        response_kind="raw", version_present=True)
    _bind(dashboard_module, "_dispatch_parse_error", shim)(perr)
    assert shim.raw_direct_calls == [(400, "bad", True)]


# ── _send_json extension backwards compat ──────────────────────

def test_send_json_default_cache_control_is_no_cache(
        dashboard_module):
    """Existing shipped consumers do NOT pass `cache_control`;
    they must continue to see `Cache-Control: no-cache` — the
    B1 extension is additive only.
    """
    shim = _FakeHandler()
    _bind(dashboard_module, "_send_json", shim)({"ok": True})
    values = dict(shim.headers)
    assert values["Cache-Control"] == "no-cache"
    assert values["Content-Type"] == "application/json; charset=utf-8"
    assert values["X-Content-Type-Options"] == "nosniff"


def test_send_json_no_store_when_requested(dashboard_module):
    shim = _FakeHandler()
    _bind(dashboard_module, "_send_json", shim)(
        {"error": "x"}, status=404, cache_control="no-store")
    values = dict(shim.headers)
    assert values["Cache-Control"] == "no-store"


def test_send_json_error_envelope_and_status(dashboard_module):
    shim = _FakeHandler()
    # _send_json_error delegates to _send_json — bind both so
    # the shim satisfies the delegation contract.
    shim._send_json = _bind(dashboard_module, "_send_json", shim)
    _bind(dashboard_module, "_send_json_error", shim)(
        400, "invalid", cache_control="no-store")
    body = shim.wfile.getvalue().decode("utf-8")
    import json
    parsed = json.loads(body)
    assert parsed == {"error": "invalid", "code": 400}
    assert shim.status_calls == [(400, None)]
    values = dict(shim.headers)
    assert values["Cache-Control"] == "no-store"
