"""
Страница «Мониторинг» — метрики и графики системы.
"""

import random
import time
from datetime import datetime, timedelta

import streamlit as st

from utils.api_client import VagusAPIClient

st.set_page_config(page_title="Мониторинг — Vagus", page_icon="📊", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("Пожалуйста, войдите в систему на главной странице.")
    st.stop()

st.title("📊 Мониторинг")
st.markdown("Системные метрики и состояние Vagus Asistent в реальном времени.")
st.divider()

client = VagusAPIClient()


def _safe_system_status() -> dict:
    """Загружает статус системы; при ошибке возвращает заглушку."""
    try:
        return client.get_system_status()
    except Exception:
        return {}


status = _safe_system_status()

# ── top-level metrics ────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Статус",
        "Online" if status else "Offline",
        delta="ok" if status else "err",
    )
with col2:
    st.metric("Активные агенты", status.get("active_agents", "—"))
with col3:
    st.metric("Задач сегодня", status.get("tasks_today", "—"))
with col4:
    uptime_s = status.get("uptime_seconds")
    if uptime_s is not None:
        hours = int(uptime_s) // 3600
        mins = (int(uptime_s) % 3600) // 60
        st.metric("Аптайм", f"{hours}ч {mins}м")
    else:
        st.metric("Аптайм", "—")

st.divider()

# ── detailed metrics ─────────────────────────────────────────────────────────

st.subheader("Детальные метрики")

metrics = status.get("metrics", {})
if metrics:
    mcols = st.columns(min(len(metrics), 4))
    for idx, (key, val) in enumerate(metrics.items()):
        with mcols[idx % len(mcols)]:
            label = key.replace("_", " ").title()
            st.metric(label, val)
elif status:
    st.info("Детальные метрики недоступны в ответе API.")
else:
    st.info("Не удалось получить данные от API. Проверьте подключение.")

st.divider()

# ── charts ───────────────────────────────────────────────────────────────────

st.subheader("Графики")

latency_history = status.get("latency_history", [])
tasks_history = status.get("tasks_history", [])

tab_latency, tab_tasks, tab_errors = st.tabs(
    ["Задержка (latency)", "Задачи", "Ошибки"]
)

try:
    import plotly.graph_objects as go

    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False


def _demo_timeseries(n: int = 30) -> dict:
    """Генерирует демо-данные, если API ещё не отдаёт историю."""
    now = datetime.now()
    dates = [(now - timedelta(minutes=n - i)).strftime("%H:%M") for i in range(n)]
    return {"dates": dates}


demo = _demo_timeseries()

with tab_latency:
    if latency_history:
        data = latency_history
    else:
        data = [random.uniform(80, 250) for _ in range(30)]
        st.caption("Демо-данные (API не вернул latency_history)")

    if _HAS_PLOTLY:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=demo["dates"], y=data,
            mode="lines+markers",
            name="Latency (ms)",
            line=dict(color="#636EFA", width=2),
        ))
        fig.update_layout(
            yaxis_title="ms",
            xaxis_title="Время",
            height=350,
            margin=dict(l=40, r=20, t=30, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.line_chart(data)

with tab_tasks:
    if tasks_history:
        data = tasks_history
    else:
        data = [random.randint(5, 50) for _ in range(30)]
        st.caption("Демо-данные (API не вернул tasks_history)")

    if _HAS_PLOTLY:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=demo["dates"], y=data,
            name="Задачи",
            marker_color="#00CC96",
        ))
        fig.update_layout(
            yaxis_title="Количество",
            xaxis_title="Время",
            height=350,
            margin=dict(l=40, r=20, t=30, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(data)

with tab_errors:
    errors = status.get("error_history", [])
    if errors:
        data = errors
    else:
        data = [random.randint(0, 5) for _ in range(30)]
        st.caption("Демо-данные (API не вернул error_history)")

    if _HAS_PLOTLY:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=demo["dates"], y=data,
            mode="lines",
            name="Ошибки",
            fill="tozeroy",
            line=dict(color="#EF553B", width=2),
        ))
        fig.update_layout(
            yaxis_title="Количество",
            xaxis_title="Время",
            height=350,
            margin=dict(l=40, r=20, t=30, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.line_chart(data)

# ── auto-refresh ─────────────────────────────────────────────────────────────

st.divider()
auto = st.checkbox("Автообновление (каждые 10 с)", value=False)
if auto:
    time.sleep(10)
    st.rerun()
