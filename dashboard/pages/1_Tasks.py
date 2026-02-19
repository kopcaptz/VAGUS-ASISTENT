"""
Страница «Задачи» — создание задач и отслеживание результата.
"""

import time

import streamlit as st

from utils.api_client import VagusAPIClient

st.set_page_config(page_title="Задачи — Vagus", page_icon="📝", layout="wide")

# ── guard ────────────────────────────────────────────────────────────────────

if not st.session_state.get("authenticated"):
    st.warning("Пожалуйста, войдите в систему на главной странице.")
    st.stop()

# ── header ───────────────────────────────────────────────────────────────────

st.title("📝 Задачи")
st.markdown("Создайте задачу и получите результат от системы Vagus Asistent.")
st.divider()

client = VagusAPIClient()

TASK_TYPES = [
    "default",
    "research",
    "analysis",
    "code",
    "summarize",
    "translate",
]

# ── form ─────────────────────────────────────────────────────────────────────

with st.form("task_form"):
    prompt = st.text_area(
        "Промпт",
        height=160,
        placeholder="Опишите задачу, которую нужно выполнить...",
    )
    col_type, col_submit = st.columns([3, 1])
    with col_type:
        task_type = st.selectbox("Тип задачи", TASK_TYPES)
    with col_submit:
        st.write("")  # vertical spacer
        submitted = st.form_submit_button(
            "🚀 Запустить", use_container_width=True,
        )

# ── execution ────────────────────────────────────────────────────────────────

if submitted:
    if not prompt.strip():
        st.error("Введите промпт перед запуском.")
        st.stop()

    result_container = st.container()

    with result_container:
        status_placeholder = st.empty()
        progress_bar = st.progress(0, text="Отправка задачи...")

    try:
        task_data = client.create_task(prompt=prompt, task_type=task_type)
        task_id = task_data.get("task_id") or task_data.get("id")
        if not task_id:
            st.error(f"API не вернул task_id: {task_data}")
            st.stop()

        status_placeholder.info(f"Задача создана: `{task_id}`. Ожидание результата...")
        progress_bar.progress(10, text="Задача создана, ожидание...")

        max_polls = 240
        for i in range(max_polls):
            time.sleep(0.5)

            task_status = client.get_task_status(task_id)
            current = task_status.get("status", "unknown")

            pct = min(10 + int((i / max_polls) * 85), 95)
            progress_bar.progress(pct, text=f"Статус: {current}")

            if current == "completed":
                progress_bar.progress(100, text="Готово!")
                result = task_status.get("result", "")
                if isinstance(result, dict):
                    result = result.get("answer", result.get("text", str(result)))
                status_placeholder.success("Задача выполнена!")
                st.markdown("### Результат")
                st.markdown(str(result))
                break

            if current == "failed":
                error = task_status.get("error", "Неизвестная ошибка")
                progress_bar.progress(100, text="Ошибка")
                status_placeholder.error(f"Задача завершилась с ошибкой: {error}")
                break
        else:
            progress_bar.progress(100, text="Таймаут")
            status_placeholder.warning(
                "Превышено время ожидания (120 с). Задача всё ещё выполняется — "
                "проверьте позже."
            )

    except Exception as exc:
        st.error(f"Ошибка при взаимодействии с API: {exc}")

# ── history (session-based) ──────────────────────────────────────────────────

st.divider()
st.markdown("### 📋 История запросов (сессия)")

if "task_history" not in st.session_state:
    st.session_state["task_history"] = []

if submitted and prompt.strip():
    st.session_state["task_history"].insert(0, {
        "prompt": prompt[:120],
        "type": task_type,
        "time": time.strftime("%H:%M:%S"),
    })

if st.session_state["task_history"]:
    for idx, entry in enumerate(st.session_state["task_history"][:20]):
        st.caption(
            f"**{entry['time']}** | `{entry['type']}` — {entry['prompt']}"
        )
else:
    st.caption("Пока нет запросов в этой сессии.")
