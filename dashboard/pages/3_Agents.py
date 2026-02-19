"""
Страница «Агенты» — список, статус и управление агентами.
"""

import streamlit as st

from utils.api_client import VagusAPIClient

st.set_page_config(page_title="Агенты — Vagus", page_icon="🤖", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("Пожалуйста, войдите в систему на главной странице.")
    st.stop()

st.title("🤖 Агенты")
st.markdown("Управление агентами системы Vagus Asistent.")
st.divider()

client = VagusAPIClient()


def _load_agents() -> list:
    try:
        return client.get_agents()
    except Exception as exc:
        st.error(f"Не удалось загрузить агентов: {exc}")
        return []


agents = _load_agents()

if not agents:
    st.info(
        "Нет данных об агентах. Убедитесь, что API запущен и доступен."
    )
    st.stop()

# ── summary metrics ──────────────────────────────────────────────────────────

total = len(agents)
active = sum(1 for a in agents if a.get("enabled", a.get("active", True)))
inactive = total - active

col1, col2, col3 = st.columns(3)
col1.metric("Всего агентов", total)
col2.metric("Активные", active)
col3.metric("Неактивные", inactive)

st.divider()

# ── agents table with toggles ───────────────────────────────────────────────

st.subheader("Список агентов")

for idx, agent in enumerate(agents):
    agent_id = agent.get("id", agent.get("name", f"agent_{idx}"))
    name = agent.get("name", agent_id)
    description = agent.get("description", "—")
    task_types = agent.get("task_types", [])
    enabled = agent.get("enabled", agent.get("active", True))

    with st.container():
        c_info, c_types, c_toggle = st.columns([4, 3, 2])

        with c_info:
            status_icon = "🟢" if enabled else "🔴"
            st.markdown(f"**{status_icon} {name}**")
            st.caption(description)

        with c_types:
            if task_types:
                st.markdown(
                    " ".join(f"`{t}`" for t in task_types)
                )
            else:
                st.caption("—")

        with c_toggle:
            new_state = st.toggle(
                "Включён",
                value=enabled,
                key=f"agent_toggle_{agent_id}",
            )
            if new_state != enabled:
                try:
                    client.toggle_agent(str(agent_id), new_state)
                    st.success(
                        f"{'Включён' if new_state else 'Выключен'}: {name}"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Ошибка переключения: {exc}")

        st.divider()

# ── raw json expander ────────────────────────────────────────────────────────

with st.expander("Сырые данные (JSON)"):
    st.json(agents)
