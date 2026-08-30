"""
Tests for the Blueprints 2.0 Release A shipped assets and endpoint.

Covers:
- Structural conformance of the shipped l1-data.json + l1-positions.json
  (both live under src/gator_command/scripts/dashboard/blueprint/).
- Cross-file consistency: every node id in l1-data.json has a position
  entry in l1-positions.json.
- Endpoint behavior: /api/repo/<name>/blueprint returns the merged Gator
  L1 payload for the Gator source repo, and returns a structured
  unavailable-state response for a non-Gator repo (the r2 whiteboard
  finding pin — no silent fallback to Gator's own dataset when the
  active repo isn't the Gator source).

Endpoint tests exercise the handler class directly via a mock request
rather than starting an HTTP server; keeps the suite fast + deterministic.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "src" / "gator_command" / "scripts"
BLUEPRINT_DIR = SCRIPTS_DIR / "dashboard" / "blueprint"
DATA_FILE = BLUEPRINT_DIR / "l1-data.json"
POSITIONS_FILE = BLUEPRINT_DIR / "l1-positions.json"


# ── shipped asset shape ─────────────────────────────────────────────────


class TestL1DataShape:
    """Structural pin on the shipped l1-data.json — the Release A dataset
    that fleet repos will see (via the endpoint's Gator-source-repo gate)
    and that Release B's parser must be able to reproduce byte-compatibly."""

    def setup_method(self):
        self.data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    def test_file_exists(self):
        assert DATA_FILE.is_file(), (
            f"Release A ships this file; endpoint gate uses its presence "
            f"as the Gator-source-repo detection signal. Path: {DATA_FILE}"
        )

    def test_top_level_shape(self):
        assert self.data.get("level") == 1
        assert "generated_at" in self.data
        assert isinstance(self.data.get("nodes"), list)
        assert isinstance(self.data.get("edges"), list)

    def test_nodes_have_required_fields(self):
        required = {"id", "title", "kind", "color", "summary", "covers", "functions"}
        for node in self.data["nodes"]:
            missing = required - set(node.keys())
            assert not missing, f"node {node.get('id')!r} missing fields: {missing}"
            assert isinstance(node["covers"], list)
            assert isinstance(node["functions"], list)

    def test_node_ids_are_unique(self):
        ids = [n["id"] for n in self.data["nodes"]]
        assert len(ids) == len(set(ids)), f"duplicate node ids in l1-data.json: {ids}"

    def test_edges_reference_real_nodes(self):
        ids = {n["id"] for n in self.data["nodes"]}
        for edge in self.data["edges"]:
            assert edge["from"] in ids, f"edge from unknown node: {edge}"
            assert edge["to"] in ids, f"edge to unknown node: {edge}"
            assert "label" in edge

    def test_reasonable_dataset_size(self):
        """Regression pin: Release A extraction produced 13 nodes / 29 edges.
        Release B parser should produce at LEAST this many; going smaller
        without a curated reduction is a regression."""
        assert len(self.data["nodes"]) >= 13, (
            f"expected ≥13 nodes (Release A baseline), got {len(self.data['nodes'])}"
        )
        assert len(self.data["edges"]) >= 25, (
            f"expected ≥25 edges (Release A baseline), got {len(self.data['edges'])}"
        )


class TestL1Positions:
    def setup_method(self):
        self.positions = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
        self.data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    def test_file_exists(self):
        assert POSITIONS_FILE.is_file()

    def test_shape(self):
        assert "positions" in self.positions
        assert "canvas" in self.positions
        assert isinstance(self.positions["canvas"].get("width"), int)
        assert isinstance(self.positions["canvas"].get("height"), int)

    def test_every_data_node_has_a_position(self):
        """Cross-file consistency: l1-positions.json is the overlay Release B's
        parser will preserve while regenerating l1-data.json. Any node in
        data without a matching position becomes a floating auto-layout
        node — noise-inducing if unexpected."""
        pos_ids = set(self.positions["positions"].keys())
        data_ids = {n["id"] for n in self.data["nodes"]}
        missing = data_ids - pos_ids
        assert not missing, (
            f"nodes in l1-data.json without positions in l1-positions.json: "
            f"{sorted(missing)}"
        )

    def test_every_position_has_a_data_node(self):
        """The reverse — a position for a nonexistent node is stale drift."""
        pos_ids = set(self.positions["positions"].keys())
        data_ids = {n["id"] for n in self.data["nodes"]}
        orphans = pos_ids - data_ids
        assert not orphans, (
            f"positions in l1-positions.json for nonexistent nodes: "
            f"{sorted(orphans)}"
        )

    def test_position_values_are_ints(self):
        for node_id, pos in self.positions["positions"].items():
            assert isinstance(pos.get("x"), int), f"non-int x for {node_id}: {pos}"
            assert isinstance(pos.get("y"), int), f"non-int y for {node_id}: {pos}"


# ── endpoint behavior ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def dashboard_module():
    """Load gator-dashboard.py via importlib so we can call the handler
    class directly. Follows the load_script pattern used elsewhere."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from conftest import load_script
    return load_script("gator-dashboard")


class _MockHandler:
    """Minimal mock of DashboardHandler enough to exercise do_GET's
    blueprint branch. Captures the last _send_json call so tests can
    assert on the response."""

    def __init__(self, path):
        self.path = path
        self.sent_json = None
        self.sent_status = None

    def _send_json(self, payload, status=200):
        self.sent_json = payload
        self.sent_status = status


def _dispatch(dashboard_module, path, monkeypatch=None):
    """Invoke DashboardHandler.do_GET with a mock request."""
    handler = _MockHandler(path)
    handler.__class__ = dashboard_module.DashboardHandler
    # Re-init __dict__ manually since we skipped __init__
    handler.path = path
    handler.sent_json = None
    handler.sent_status = None
    # Attach our capture method
    handler._send_json = _MockHandler._send_json.__get__(handler, handler.__class__)
    dashboard_module.DashboardHandler.do_GET(handler)
    return handler


class TestBlueprintEndpointGatorSourceRepo:
    """When the request resolves to the Gator source repo (on-disk
    detection: repo contains src/gator_command/scripts/dashboard/blueprint/l1-data.json),
    the endpoint returns the merged L1 payload."""

    def test_returns_merged_payload_for_gator_source(self, dashboard_module, monkeypatch, tmp_path):
        # Build a fake registry pointing 'gator' at THIS repo (which IS the
        # Gator source repo — the shipped data files live under its src/).
        monkeypatch.setattr(dashboard_module, "_REGISTRY_REPOS", [
            {"name": "gator", "path": str(REPO_ROOT)},
        ])
        handler = _dispatch(dashboard_module, "/api/repo/gator/blueprint?level=1")
        assert handler.sent_json is not None
        payload = handler.sent_json
        assert payload.get("level") == 1
        assert payload.get("status") != "unavailable", (
            f"Gator source repo must serve the L1 payload, not empty-state. Got: {payload!r}"
        )
        assert isinstance(payload.get("nodes"), list) and payload["nodes"]
        # Positions merged into node objects
        for node in payload["nodes"]:
            assert "x" in node and "y" in node, (
                f"merged payload must inject positions into nodes; missing on {node.get('id')!r}"
            )
        assert "canvas" in payload


class TestBlueprintEndpointNonGatorRepo:
    """LOAD-BEARING (r2 whiteboard finding 2 pin): when the active repo
    is NOT the Gator source, the endpoint MUST return a structured
    unavailable-state, never fall back to serving the Gator dataset.
    Serving Gator's charter map under another repo's name is exactly
    the "wrong data at the per-repo seam" mistake the r2 revision fixed."""

    def test_returns_unavailable_for_non_gator(self, dashboard_module, monkeypatch, tmp_path):
        # Set up a fake repo directory that does NOT have the shipped data.
        fake_repo = tmp_path / "fake-repo"
        fake_repo.mkdir()
        (fake_repo / ".gator").mkdir()  # looks gatorized, but has no blueprint data
        monkeypatch.setattr(dashboard_module, "_REGISTRY_REPOS", [
            {"name": "fake-repo", "path": str(fake_repo)},
        ])
        handler = _dispatch(dashboard_module, "/api/repo/fake-repo/blueprint?level=1")
        assert handler.sent_json is not None
        payload = handler.sent_json
        assert payload.get("status") == "unavailable", (
            f"non-Gator repo must NOT receive Gator's dataset; expected structured "
            f"unavailable-state. Got: {payload!r}"
        )
        assert payload.get("reason") == "release-b-pending"
        assert "message" in payload
        # And critically: no nodes/edges leaked from the Gator dataset.
        assert "nodes" not in payload
        assert "edges" not in payload


class TestBlueprintEndpointOtherLevels:
    def test_level_2_returns_501(self, dashboard_module, monkeypatch, tmp_path):
        monkeypatch.setattr(dashboard_module, "_REGISTRY_REPOS", [
            {"name": "gator", "path": str(REPO_ROOT)},
        ])
        handler = _dispatch(dashboard_module, "/api/repo/gator/blueprint?level=2")
        assert handler.sent_status == 501
        assert "not yet implemented" in handler.sent_json.get("error", "")


class TestBlueprintEndpointShippedDataUnreadable:
    """LOAD-BEARING (2026-08-30 whiteboard finding): the `status: "unavailable"`
    response shape is used for BOTH the intentional Release A gate
    (`reason: "release-b-pending"`, informational empty-state) AND for
    real degradation (`reason: "shipped-data-unreadable"`, actual error).
    The frontend must branch on `reason` and NOT dress a corrupt-shipped-
    data failure as a "Release B will fix it" message. This test pins the
    endpoint-side distinction; the frontend branch is in `views/blueprint.js`
    and can only be exercised through a browser session, so this
    regression pin at least guarantees the differentiating `reason`
    field is present in the payload."""

    def test_shipped_data_unreadable_returns_distinct_reason(
        self, dashboard_module, monkeypatch, tmp_path
    ):
        # Point the dashboard's DASHBOARD_DIR at a tmp dir where the
        # shipped blueprint files don't exist — the OSError → JSONDecodeError
        # chain triggers the shipped-data-unreadable branch.
        empty_dashboard = tmp_path / "fake-dashboard"
        empty_dashboard.mkdir()
        monkeypatch.setattr(dashboard_module, "DASHBOARD_DIR", empty_dashboard)
        # Registry still points at THIS repo so the Gator-source-repo gate
        # passes (the gate looks at repo path, not at DASHBOARD_DIR).
        monkeypatch.setattr(dashboard_module, "_REGISTRY_REPOS", [
            {"name": "gator", "path": str(REPO_ROOT)},
        ])
        handler = _dispatch(dashboard_module, "/api/repo/gator/blueprint?level=1")
        assert handler.sent_json is not None
        payload = handler.sent_json
        assert payload.get("status") == "unavailable"
        assert payload.get("reason") == "shipped-data-unreadable", (
            f"corrupt/missing shipped data must produce a DISTINCT reason "
            f"from the release-b-pending gate, not the same shape. "
            f"Got: {payload!r}"
        )
        assert "message" in payload, (
            "message field required so frontend renderErrorState can display "
            "operator-actionable copy (not the empty-state 'Release B ships' "
            "text)"
        )
        assert "detail" in payload
        # And critically: MUST NOT carry the release-b-pending reason,
        # which the frontend routes to renderEmptyState with wrong copy.
        assert payload.get("reason") != "release-b-pending"

    def test_release_b_pending_and_shipped_data_unreadable_are_different_reasons(
        self, dashboard_module, monkeypatch, tmp_path
    ):
        """Guardrail: the two 'unavailable' branches must use different
        `reason` values. If someone unifies them, the frontend loses the
        ability to distinguish informational-empty-state from real-error."""
        # release-b-pending path (non-Gator repo)
        fake_repo = tmp_path / "non-gator-repo"
        fake_repo.mkdir()
        (fake_repo / ".gator").mkdir()
        monkeypatch.setattr(dashboard_module, "_REGISTRY_REPOS", [
            {"name": "non-gator-repo", "path": str(fake_repo)},
        ])
        handler_a = _dispatch(
            dashboard_module, "/api/repo/non-gator-repo/blueprint?level=1"
        )
        reason_a = handler_a.sent_json.get("reason")
        # shipped-data-unreadable path
        empty_dashboard = tmp_path / "fake-dashboard-2"
        empty_dashboard.mkdir()
        monkeypatch.setattr(dashboard_module, "DASHBOARD_DIR", empty_dashboard)
        monkeypatch.setattr(dashboard_module, "_REGISTRY_REPOS", [
            {"name": "gator", "path": str(REPO_ROOT)},
        ])
        handler_b = _dispatch(
            dashboard_module, "/api/repo/gator/blueprint?level=1"
        )
        reason_b = handler_b.sent_json.get("reason")
        assert reason_a != reason_b, (
            f"the two branches must carry distinct reasons; "
            f"non-gator={reason_a!r} shipped-unreadable={reason_b!r}"
        )
        assert reason_a == "release-b-pending"
        assert reason_b == "shipped-data-unreadable"
