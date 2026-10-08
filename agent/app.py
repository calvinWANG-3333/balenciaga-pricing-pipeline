"""Streamlit front-end of the agent:  streamlit run agent/app.py

Ask      a question -> what was understood, the answer, the SQL, the source (or a reasoned refusal)
Triage   the delivery gate's WARN / BLOCK verdicts, explained with evidence
Metrics  the governed catalogue, straight from the dbt semantic layer
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run from anywhere

import streamlit as st  # noqa: E402

from agent import semantic  # noqa: E402
from agent.cli import build_agent  # noqa: E402
from agent.triage import Triage, render_markdown  # noqa: E402
from qa.config import Settings  # noqa: E402

st.set_page_config(page_title="Balenciaga pricing - metrics agent", layout="wide")


@st.cache_resource(show_spinner="Connecting to the warehouse and loading the semantic layer ...")
def get_agent(translator: str):
    return build_agent(Settings.from_env(), translator)


st.title("Balenciaga pricing - metrics agent")
st.caption("Answers only governed metrics from the dbt semantic layer, on released deliveries only. "
           "Questions are translated to a structured form; guardrails decide; the SQL is a template.")

with st.sidebar:
    translator = st.radio("Translator", ["auto", "rules", "claude"], index=0,
                          help="auto = Claude if ANTHROPIC_API_KEY is set, otherwise the offline rules")
    use_llm = st.checkbox("Let Claude phrase the answer", value=False)
    st.markdown("**Try:**")
    examples = ["How much is the Le City bag in the USA?",
                "Which market had the highest bag price increase last month?",
                "How much did prices change in September by category?",
                "What is the median price of bags?",
                "How many price increases were there in Japan in September?",
                "LFL change for shoes in Germany"]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["question"] = ex

ask_tab, triage_tab, metrics_tab = st.tabs(["Ask", "Triage", "Metrics"])

with ask_tab:
    question = st.text_input("Question", key="question", placeholder="Ask about hero prices, categories, price changes ...")
    if question:
        agent = get_agent(translator)
        answer = agent.ask(question, use_llm_narration=use_llm)
        if answer.refusal:
            st.warning(f"**I can't answer that:** {answer.refusal.reason}")
            if answer.refusal.suggestion:
                st.info(answer.refusal.suggestion)
        else:
            i = answer.intent
            filters = ", ".join(f"{k} = {' / '.join(v)}" for k, v in i.filters.items()) or "none"
            by = ", ".join((["time"] if i.group_by_time else []) + i.group_by) or "none"
            st.markdown(f"**Understood as** metric `{i.metric}` · period *{i.time_label}* · "
                        f"filters *{filters}* · by *{by}*  \n<sub>translator: {answer.translator}</sub>",
                        unsafe_allow_html=True)
            for note in i.notes:
                st.caption(f"Note: {note}")
            st.markdown(answer.llm_text or answer.text)
            if answer.llm_text:
                with st.expander("Deterministic answer"):
                    st.markdown(answer.text)
            st.caption(answer.provenance)
            with st.expander("SQL (compiled from the semantic layer)"):
                st.code(answer.sql, language="sql")
            with st.expander("Structured question (what the translator produced)"):
                st.json(i.to_dict())

with triage_tab:
    c1, c2, c3 = st.columns(3)
    dataset = c1.selectbox("Dataset", ["marts", "legacy_replay"])
    scope = c2.selectbox("Scope", ["all", "micro", "macro"])
    as_of = c3.text_input("Delivery date (optional)", placeholder="YYYY-MM-DD")
    if st.button("Run triage"):
        agent = get_agent(translator)
        notes = Triage(agent.db, Settings.from_env()).review(
            dataset, None if scope == "all" else scope, date.fromisoformat(as_of) if as_of else None)
        st.markdown(render_markdown(notes))

with metrics_tab:
    cat = semantic.load()
    for m in cat.public_metrics():
        model = cat.model_of(m)
        with st.expander(f"{m.label}  -  `{m.name}`"):
            st.write(m.description)
            st.markdown(f"- unit: **{m.unit}**\n- source: `{model.alias}` (semantic model `{model.name}`)\n"
                        f"- dimensions: {', '.join(d for d in model.dimensions if d != model.time_dimension)}\n"
                        f"- time: `{model.time_dimension}`"
                        + (f"\n- requires: {', '.join(m.requires)}" if m.requires else ""))
