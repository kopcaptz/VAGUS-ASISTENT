"""Страница real-time мониторинга системы."""

from __future__ import annotations

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    try:
        from dashboard.utils.api_client import VagusAPIClient
        from dashboard.utils.auth import attach_unauthorized_handler, get_token, require_login
        from dashboard.utils.artifact_graph import build_networkx_graph, fetch_graph_data
        from dashboard.utils.postgres_monitor import fetch_postgres_metrics
        from dashboard.utils.redis_monitor import fetch_redis_metrics
    except ModuleNotFoundError:
        from utils.api_client import VagusAPIClient
        from utils.auth import attach_unauthorized_handler, get_token, require_login
        from utils.artifact_graph import build_networkx_graph, fetch_graph_data
        from utils.postgres_monitor import fetch_postgres_metrics
        from utils.redis_monitor import fetch_redis_metrics

    require_login()

    st.title("Real-Time Мониторинг")

    try:
        from streamlit_autorefresh import st_autorefresh

        st_autorefresh(interval=5000, limit=None, key="monitoring_refresh")
    except ImportError:
        pass

    client = attach_unauthorized_handler(VagusAPIClient(token=get_token()))

    # --- Synaptic Graph ---
    st.subheader("Граф синаптических связей")
    try:
        nodes, edges = fetch_graph_data(client, limit=500)
        g = build_networkx_graph(edges)
        if g and g.number_of_edges() > 0:
            try:
                import networkx as nx
                import plotly.graph_objects as go

                pos = nx.spring_layout(g, seed=42, k=0.8)
                edge_x, edge_y = [], []
                for u, v in g.edges():
                    x0, y0 = pos[u]
                    x1, y1 = pos[v]
                    edge_x.extend([x0, x1, None])
                    edge_y.extend([y0, y1, None])
                edge_trace = go.Scatter(
                    x=edge_x,
                    y=edge_y,
                    mode="lines",
                    line=dict(width=1.5, color="rgba(100,150,200,0.6)"),
                    hoverinfo="none",
                    showlegend=False,
                )
                node_x = [pos[n][0] for n in g.nodes()]
                node_y = [pos[n][1] for n in g.nodes()]
                node_trace = go.Scatter(
                    x=node_x,
                    y=node_y,
                    mode="markers+text",
                    text=[str(n)[:12] + "..." if len(str(n)) > 12 else str(n) for n in g.nodes()],
                    textposition="top center",
                    hoverinfo="text",
                    hovertext=[str(n) for n in g.nodes()],
                    marker=dict(size=12, color="lightblue", line=dict(width=1, color="gray")),
                    showlegend=False,
                )
                fig = go.Figure(data=[edge_trace, node_trace])
                fig.update_layout(
                    showlegend=False,
                    hovermode="closest",
                    margin=dict(b=20, l=20, r=20, t=40),
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    plot_bgcolor="rgba(0,0,0,0)",
                    height=400,
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption(f"Узлов: {g.number_of_nodes()}, Рёбер: {g.number_of_edges()}. Толщина/цвет — вес связи (0–1)")
            except ImportError:
                st.info("Установите networkx и plotly для визуализации графа")
                st.json([{"source_id": e["source_id"], "target_id": e["target_id"], "weight": e["weight"]} for e in edges[:20]])
        else:
            st.info("Нет данных о синаптических связях")
    except Exception as e:
        st.error(f"Ошибка загрузки графа: {e}")

    st.markdown("---")

    # --- Learning Metrics ---
    st.subheader("Метрики обучения")
    try:
        synaptic = client.get_monitoring_synaptic()
        if synaptic.get("available"):
            c1, c2, c3 = st.columns(3)
            c1.metric("quality_gate.passed", synaptic.get("events_processed", 0))
            c2.metric("Размер буфера", f"{synaptic.get('buffer_size', 0)}/{synaptic.get('buffer_size_max', 50)}")
            c3.metric("Flush операций", synaptic.get("flush_count", 0))
            flush_history = synaptic.get("flush_history") or []
            if flush_history:
                try:
                    import plotly.graph_objects as go

                    timestamps = [h[0] for h in flush_history]
                    counts = [h[1] for h in flush_history]
                    fig2 = go.Figure(data=[go.Scatter(x=timestamps, y=counts, mode="lines+markers", name="Событий за flush")])
                    fig2.update_layout(title="Усиление связей во времени (событий за flush)", height=250, xaxis_title="Время", yaxis_title="Количество")
                    st.plotly_chart(fig2, use_container_width=True)
                except ImportError:
                    st.write("Последние flush:", flush_history[-10:])
        else:
            st.warning(f"Synaptic handler недоступен: {synaptic.get('error', 'unknown')}")
    except Exception as e:
        st.error(f"Ошибка метрик обучения: {e}")

    st.markdown("---")

    # --- Redis Streams ---
    st.subheader("Redis Streams")
    try:
        redis_data = fetch_redis_metrics(client)
        if redis_data.get("available"):
            st.write("Stream:", redis_data.get("stream_name", "—"))
            groups = redis_data.get("consumer_groups") or []
            if groups:
                st.dataframe(
                    [{"Группа": g["name"], "Pending": g["pending"], "Consumers": g["consumers"], "Last ID": g["last_delivered_id"]} for g in groups],
                    use_container_width=True,
                )
            st.metric("DLQ сообщений", redis_data.get("dlq_count", 0))
        else:
            st.warning(f"Redis Streams недоступны: {redis_data.get('error', 'не включены')}")
    except Exception as e:
        st.error(f"Ошибка Redis: {e}")

    st.markdown("---")

    # --- PostgreSQL ---
    st.subheader("PostgreSQL / SQLite")
    try:
        pg_data = fetch_postgres_metrics(client)
        if pg_data.get("available"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Артефактов", pg_data.get("artifacts_count", 0))
            c2.metric("Связей", pg_data.get("relationships_count", 0))
            c3.metric("Время запроса (мс)", pg_data.get("query_time_ms", "—"))
            st.caption(f"Backend: {pg_data.get('backend', 'unknown')}")
            if pg_data.get("pool_size") is not None:
                st.metric("Активных соединений пула", pg_data["pool_size"])
        else:
            st.warning(f"БД недоступна: {pg_data.get('error', 'unknown')}")
    except Exception as e:
        st.error(f"Ошибка PostgreSQL: {e}")

    st.markdown("---")
    if st.button("Обновить вручную"):
        st.rerun()
