"""Страница управления задачами."""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    import time

    try:
        from dashboard.utils.api_client import VagusAPIClient
        from dashboard.utils.auth import attach_unauthorized_handler, get_token, require_login
    except ModuleNotFoundError:
        from utils.api_client import VagusAPIClient
        from utils.auth import attach_unauthorized_handler, get_token, require_login

    require_login()

    st.title("Задачи")

    client = attach_unauthorized_handler(VagusAPIClient(token=get_token()))

    with st.form("create_task_form"):
        prompt = st.text_area(
            "Введите запрос:",
            height=150,
            placeholder="Напиши Python-функцию для...",
        )
        task_type = st.selectbox("Тип задачи:", ["default", "research", "code", "analysis"])
        submitted = st.form_submit_button("Запустить задачу")

    if submitted and prompt:
        with st.spinner("Создание задачи..."):
            try:
                response = client.create_task(prompt=prompt, task_type=task_type)
                task_id = response["task_id"]
                st.success(f"Задача создана: `{task_id}`")

                status_ph = st.empty()
                result_ph = st.empty()

                for _ in range(60):
                    time.sleep(0.5)
                    status_data = client.get_task_status(task_id)
                    status = status_data.get("status", "")
                    status_ph.info(f"Статус: **{status}**")

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
            for t in tasks:
                col1, col2, col3 = st.columns([3, 1, 2])
                col1.code(t.get("task_id", ""))
                col2.write(t.get("status", ""))
                col3.write(str(t.get("created_at", "")))
        else:
            st.info("Нет задач")
    except Exception:
        st.info("Не удалось загрузить список задач")
