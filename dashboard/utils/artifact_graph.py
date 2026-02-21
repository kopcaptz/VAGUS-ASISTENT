"""
Утилиты для построения графа синаптических связей.
Вызывает API /monitoring/artifact-graph и строит networkx граф для визуализации.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

Client = Any


def fetch_graph_data(
    client: Client,
    *,
    tenant_id: Optional[str] = None,
    limit: int = 500,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Загружает данные графа через API.
    Returns: (nodes: list of artifact_ids, edges: [{source_id, target_id, weight}, ...])
    """
    try:
        data = client.get_monitoring_artifact_graph(tenant_id=tenant_id, limit=limit)
    except Exception:
        return [], []

    edges = data.get("edges") or []
    nodes_set: set[str] = set()
    for e in edges:
        sid = e.get("source_id")
        tid = e.get("target_id")
        if sid:
            nodes_set.add(sid)
        if tid:
            nodes_set.add(tid)
    return list(nodes_set), edges


def build_networkx_graph(edges: List[Dict[str, Any]]):
    """
    Строит networkx.DiGraph из списка рёбер.
    Рёбра имеют атрибут 'weight' (0.0-1.0).
    """
    try:
        import networkx as nx
    except ImportError:
        return None

    g = nx.DiGraph()
    for e in edges:
        sid = e.get("source_id")
        tid = e.get("target_id")
        w = float(e.get("weight", 0.5))
        if sid and tid:
            g.add_edge(sid, tid, weight=w)
    return g
