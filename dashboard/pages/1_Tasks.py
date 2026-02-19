"""
Tasks page — create tasks and view results.
"""

import time

import streamlit as st

from dashboard.utils.api_client import VagusAPIClient
from dashboard.utils.auth import require_login

require_login()

st.title("Tasks")

client = VagusAPIClient()

with st.form("create_task_form"):
    prompt = st.text_area("Enter your request:", height=150, placeholder="Write a Python function for...")
    task_type = st.selectbox("Task type:", ["default", "research", "code", "analysis"])
    submitted = st.form_submit_button("Run Task")

if submitted and prompt:
    with st.spinner("Creating task..."):
        try:
            response = client.create_task(prompt=prompt, task_type=task_type)
            task_id = response["task_id"]
            st.success(f"Task created: `{task_id}`")

            status_placeholder = st.empty()
            result_placeholder = st.empty()

            for _ in range(120):
                time.sleep(0.5)
                status_data = client.get_task_status(task_id)
                status = status_data["status"]
                status_placeholder.info(f"Status: **{status}**")

                if status == "completed":
                    result = status_data.get("result", {})
                    result_placeholder.success("Task completed!")
                    st.markdown("### Result:")
                    if isinstance(result, dict):
                        st.markdown(result.get("content", str(result)))
                    else:
                        st.markdown(str(result))
                    break
                elif status == "failed":
                    result_placeholder.error(f"Error: {status_data.get('error', 'Unknown')}")
                    break
        except Exception as e:
            st.error(f"Error creating task: {e}")

st.markdown("---")
st.subheader("Recent Tasks")

try:
    tasks = client.list_tasks(limit=10)
    if tasks:
        for task in tasks:
            with st.expander(f"{task['task_id'][:8]}... — {task['status']}"):
                st.json(task)
    else:
        st.info("No tasks yet.")
except Exception as e:
    st.warning(f"Could not load tasks: {e}")
