import streamlit as st

st.set_page_config(layout="wide")

# Place the logo at the top
st.sidebar.image("assets/pngimg.com - beaver_PNG35.png")

project_1_page = st.Page(
    page="pages/analyze_impacts.py",
    title="Analyze Impacts!",
    icon=":material/bar_chart:",
    default=True,
)

pg = st.navigation(pages=[project_1_page])
pg.run()
