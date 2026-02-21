"""Страница управления задачами."""

from __future__ import annotations

import json
import time

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    import streamlit.components.v1 as components

    try:
        from dashboard.components import render_plan, render_quality_score, render_reflection
        from dashboard.utils.api_client import VagusAPIClient
        from dashboard.utils.auth import attach_unauthorized_handler, get_token, require_login
    except ModuleNotFoundError:
        from components import render_plan, render_quality_score, render_reflection
        from utils.api_client import VagusAPIClient
        from utils.auth import attach_unauthorized_handler, get_token, require_login


def _task_events_ws_html(ws_base_url: str, task_id: str, token: str) -> str:
    """HTML/JS для Live events WebSocket по задаче."""
    ws_url = f"{ws_base_url.rstrip('/')}/ws/tasks/{task_id}?token={token}"
    ws_url_payload = json.dumps(ws_url)
    return f"""
<div style="border:1px solid #ddd;border-radius:6px;padding:8px;font-family:Arial,sans-serif;">
  <b>Live events (WebSocket)</b>
  <div id="ws-status" style="margin-top:6px;color:#666;">Connecting...</div>
  <div id="ws-events" style="margin-top:8px;max-height:280px;overflow:auto;background:#fafafa;padding:8px;border-radius:4px;"></div>
</div>
<script>
const wsUrl = {ws_url_payload};
const statusEl = document.getElementById("ws-status");
const eventsEl = document.getElementById("ws-events");
let socket = null;

function appendEvent(entry) {{
  const row = document.createElement("div");
  row.style.padding = "4px 0";
  row.style.borderBottom = "1px solid #eee";
  const ev = entry.event || entry.type || "event";
  const ts = entry.ts || entry.timestamp || new Date().toISOString();
  const data = entry.data || entry.payload || {{}};
  row.textContent = `[${{ts}}] ${{ev}}: ${{JSON.stringify(data)}}`;
  eventsEl.prepend(row);
  while (eventsEl.children.length > 120) {{
    eventsEl.removeChild(eventsEl.lastChild);
  }}
}}

function connect() {{
  socket = new WebSocket(wsUrl);
  socket.onopen = () => {{
    statusEl.textContent = "Connected";
    statusEl.style.color = "#2ecc71";
  }};
  socket.onmessage = (event) => {{
    try {{
      const payload = JSON.parse(event.data);
      appendEvent(payload);
    }} catch (e) {{
      appendEvent({{ event: "raw", data: {{ raw: event.data }} }});
    }}
  }};
  socket.onclose = () => {{
    statusEl.textContent = "Disconnected. Reconnecting...";
    statusEl.style.color = "#e67e22";
    setTimeout(connect, 1500);
  }};
  socket.onerror = () => {{
    statusEl.textContent = "Socket error";
    statusEl.style.color = "#e74c3c";
  }};
}}

connect();
</script>
"""


def _render_task_detail(
    client: VagusAPIClient,
    task_id: str,
    status_data: dict,
    token: str,
    show_ws: bool = True,
) -> None:
    """Рендерит детальный вид задачи: план, качество, рефлексия, WebSocket."""
    plan = status_data.get("plan")
    if plan:
        with st.expander("План выполнения", expanded=True):
            render_plan(plan)

    if status_data.get("quality_score") is not None:
        with st.expander("Оценка качества", expanded=True):
            render_quality_score(status_data.get("quality_score"))

    if status_data.get("reflection_count") is not None:
        with st.expander("Циклы рефлексии", expanded=True):
            render_reflection(status_data.get("reflection_count"))

    if show_ws and token:
        st.markdown("#### Live events (WebSocket)")
        components.html(
            _task_events_ws_html(
                ws_base_url=client.websocket_root_url,
                task_id=task_id,
                token=token,
            ),
            height=320,
            scrolling=False,
        )


if STREAMLIT_AVAILABLE:
    require_login()

    st.title("Задачи")

    client = attach_unauthorized_handler(VagusAPIClient(token=get_token()))
    token_value = get_token()

    if "selected_task_id" not in st.session_state:
        st.session_state["selected_task_id"] = None

    selected = st.session_state["selected_task_id"]
    if selected:
        st.markdown(f"### Детали задачи `{selected}`")
        if st.button("← Назад к списку"):
            st.session_state["selected_task_id"] = None
            st.rerun()
        try:
            status_data = client.get_task_status(selected)
            status = status_data.get("status", "")
            st.info(f"Статус: **{status}**")
            _render_task_detail(
                client=client,
                task_id=selected,
                status_data=status_data,
                token=token_value or "",
                show_ws=True,
            )
            if status == "completed":
                result = status_data.get("result", {})
                st.markdown("### Результат:")
                if isinstance(result, dict):
                    st.markdown(result.get("content", str(result)))
                else:
                    st.write(result)
            elif status == "failed":
                st.error(f"Ошибка: {status_data.get('error', 'Unknown')}")
        except Exception as e:
            st.error(f"Ошибка загрузки: {e}")
        st.markdown("---")

    with st.form("create_task_form"):
        prompt = st.text_area(
            "Введите запрос:",
            height=150,
            placeholder="Напиши Python-функцию для...",
        )
        goal = st.text_input(
            "Цель (опционально):",
            placeholder="Целевой результат для сложных многошаговых задач",
            key="task_goal",
        )
        task_type = st.selectbox("Тип задачи:", ["default", "research", "code", "analysis"])
        submitted = st.form_submit_button("Запустить задачу")

    if submitted and prompt:
        with st.spinner("Создание задачи..."):
            try:
                response = client.create_task(
                    prompt=prompt,
                    task_type=task_type,
                    goal=goal.strip() if goal else None,
                )
                task_id = response["task_id"]
                st.success(f"Задача создана: `{task_id}`")

                status_ph = st.empty()
                result_ph = st.empty()
                detail_ph = st.empty()
                ws_ph = st.empty()
                ws_rendered = False

                for _ in range(60):
                    time.sleep(0.5)
                    status_data = client.get_task_status(task_id)
                    status = status_data.get("status", "")
                    status_ph.info(f"Статус: **{status}**")

                    with detail_ph.container():
                        if status_data.get("plan"):
                            with st.expander("План выполнения", expanded=True):
                                render_plan(status_data.get("plan"))
                        if status_data.get("quality_score") is not None:
                            with st.expander("Оценка качества", expanded=True):
                                render_quality_score(status_data.get("quality_score"))
                        if status_data.get("reflection_count") is not None:
                            with st.expander("Циклы рефлексии", expanded=True):
                                render_reflection(status_data.get("reflection_count"))

                    if not ws_rendered:
                        with ws_ph.container():
                            st.markdown("#### Live events (WebSocket)")
                            components.html(
                                _task_events_ws_html(
                                    ws_base_url=client.websocket_root_url,
                                    task_id=task_id,
                                    token=token_value or "",
                                ),
                                height=280,
                                scrolling=False,
                            )
                        ws_rendered = True

                    if status == "completed":
                        result = status_data.get("result", {})
                        result_ph.success("Задача выполнена!")
                        st.markdown("### Результат:")
                        if isinstance(result, dict):
                            st.markdown(result.get("content", str(result)))
                        else:
                            st.write(result)
                        break
                    elif status == "failed":
                        result_ph.error(f"Ошибка: {status_data.get('error', 'Unknown')}")
                        break
            except Exception as e:
                st.error(f"Ошибка: {e}")

    st.markdown("---")
    st.subheader("Последние задачи")
    try:
        tasks = client.list_tasks(limit=10)
        if tasks:
            for i, t in enumerate(tasks):
                tid = t.get("task_id") or f"task_{i}"
                col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
                col1.code(tid)
                col2.write(t.get("status", ""))
                col3.write(str(t.get("created_at", "")))
                with col4:
                    if st.button("Подробнее", key=f"detail_{tid}"):
                        st.session_state["selected_task_id"] = tid
                        st.rerun()
        else:
            st.info("Нет задач")
    except Exception:
        st.info("Не удалось загрузить список задач")
