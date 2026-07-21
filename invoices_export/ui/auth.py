import hmac
import os

import streamlit as st


def require_authentication() -> None:
    expected = os.getenv("APP_PASSWORD", "")
    if not expected:
        st.error("APP_PASSWORD is not configured.")
        st.stop()
    if st.session_state.get("authenticated"):
        return

    st.title("CNET Aging")
    supplied = st.text_input("Password", type="password")
    if st.button("Sign in", type="primary"):
        if hmac.compare_digest(supplied, expected):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Invalid password")
    st.stop()
