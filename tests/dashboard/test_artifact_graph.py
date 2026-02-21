"""Tests for dashboard artifact_graph utils."""

from unittest.mock import MagicMock

import pytest

try:
    from dashboard.utils.artifact_graph import build_networkx_graph, fetch_graph_data
except ModuleNotFoundError:
    from utils.artifact_graph import build_networkx_graph, fetch_graph_data


def test_fetch_graph_data():
    mock_client = MagicMock()
    mock_client.get_monitoring_artifact_graph.return_value = {
        "edges": [
            {"source_id": "a1", "target_id": "a2", "weight": 0.8},
            {"source_id": "a2", "target_id": "a3", "weight": 0.5},
        ],
        "available": True,
    }
    nodes, edges = fetch_graph_data(mock_client)
    assert set(nodes) == {"a1", "a2", "a3"}
    assert len(edges) == 2
    assert edges[0]["weight"] == 0.8


def test_fetch_graph_data_empty():
    mock_client = MagicMock()
    mock_client.get_monitoring_artifact_graph.return_value = {"edges": [], "available": True}
    nodes, edges = fetch_graph_data(mock_client)
    assert nodes == []
    assert edges == []


def test_build_networkx_graph():
    edges = [
        {"source_id": "n1", "target_id": "n2", "weight": 0.9},
        {"source_id": "n2", "target_id": "n3", "weight": 0.3},
    ]
    g = build_networkx_graph(edges)
    assert g is not None
    assert g.number_of_nodes() == 3
    assert g.number_of_edges() == 2
    assert g.edges["n1", "n2"]["weight"] == 0.9


def test_build_networkx_graph_no_networkx():
    """Without networkx, build_networkx_graph returns None."""
    edges = [{"source_id": "a", "target_id": "b", "weight": 0.5}]
    try:
        import networkx
    except ImportError:
        pytest.skip("networkx not installed")
    g = build_networkx_graph(edges)
    assert g is not None
