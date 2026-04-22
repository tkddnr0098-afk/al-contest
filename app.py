from __future__ import annotations

from copy import deepcopy

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from ela_read import parse_ela_excel
from adapters import build_input_data_from_dummy, build_input_data_from_ela_result
from calc_engine import build_scenario_dataframe
from config import DEFAULT_INPUT_DATA


st.set_page_config(page_title="Power System Scenario Profile Tool", layout="wide")


def plot_load_profile_streamlit(scenario_df: pd.DataFrame) -> None:
    x = scenario_df["scenario"].astype(str)
    stacked_series = [
        ("Continuous", "continuous_load_kw", "#1f77b4"),
        ("Intermittent", "intermittent_load_kw", "#ff7f0e"),
        ("Aux", "aux_load_kw", "#2ca02c"),
        ("Propulsion", "propulsion_load_kw", "#d62728"),
        ("ESS Charge", "ess_charge_kw", "#9467bd"),
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = pd.Series([0.0] * len(scenario_df))
    for label, col, color in stacked_series:
        values = scenario_df[col].astype(float)
        ax.bar(x, values, bottom=bottom, label=label, color=color)
        bottom += values

    total_load = bottom.copy()
    max_total = float(total_load.max()) if len(total_load) else 0.0
    y_max = max_total * 1.2 if max_total > 0 else 1.0
    ax.set_ylim(0, y_max)

    for idx, total in enumerate(total_load):
        if total > 0:
            ax.text(
                idx,
                total + (y_max * 0.01),
                f"{total:.1f}",
                ha="center",
                va="bottom",
                fontsize=11,
                color="black",
                fontweight="bold",
            )

    ax.set_title("Load Profile")
    ax.set_ylabel("kW")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0)
    fig.tight_layout()
    st.pyplot(fig)

def build_editable_input_data() -> dict:
    input_data = deepcopy(build_input_data_from_dummy(DEFAULT_INPUT_DATA))

    # ELA 업로드 전에는 load 항목 기본값을 0으로 초기화
    for scenario in input_data["scenarios"]:
        scenario["continuous_load_kw"] = 0.0
        scenario["intermittent_load_raw_kw"] = 0.0
        scenario["diversity_factor"] = 1.0
        scenario["intermittent_load_kw"] = 0.0
        scenario["hotel_load_kw"] = 0.0
        scenario["deck_machinery_load_kw"] = 0.0
        scenario["aux_load_kw"] = 0.0
        scenario["propulsion_load_kw"] = 0.0

    # ELA 결과가 있으면 default 값을 ELA 값으로 덮어쓰기
    ela_df = st.session_state.get("adapter_handoff_df", None)
    ela_loaded = ela_df is not None and not ela_df.empty
    if ela_loaded:
        try:
            input_data = build_input_data_from_ela_result(ela_df, input_data)
        except Exception as e:
            st.warning(f"ELA 연동 실패: {e}")

    return input_data


def render_voyage_scenario_planner(available_scenarios: list[str]) -> None:
    st.subheader("Voyage Planning")
    voyage_count = st.number_input(
        "일일 항차 횟수",
        min_value=1,
        value=int(st.session_state.get("voyage_count", 1)),
        step=1,
        key="voyage_count",
    )
    st.caption(f"선택된 항차 횟수: {voyage_count}")

    st.markdown("**운항 시나리오 정의**")
    header_mode, header_duration, _ = st.columns([2, 1, 0.5])
    header_mode.markdown("**Mode**")
    header_duration.markdown("**duration_hr**")

    if "voyage_rows" not in st.session_state:
        default_mode = available_scenarios[0] if available_scenarios else ""
        st.session_state["voyage_rows"] = [{"mode": default_mode, "duration_hr": 0.0}]

    if st.button("＋ 행 추가", key="add_voyage_row"):
        default_mode = available_scenarios[0] if available_scenarios else ""
        st.session_state["voyage_rows"].append({"mode": default_mode, "duration_hr": 0.0})

    for idx, row in enumerate(st.session_state["voyage_rows"]):
        col_mode, col_duration, col_action = st.columns([2, 1, 0.5])
        row["mode"] = col_mode.selectbox(
            "Mode",
            options=available_scenarios if available_scenarios else [""],
            index=(available_scenarios.index(row["mode"]) if row["mode"] in available_scenarios else 0),
            key=f"voyage_mode_{idx}",
            label_visibility="collapsed",
        )
        row["duration_hr"] = col_duration.number_input(
            "duration_hr",
            min_value=0.0,
            value=float(row.get("duration_hr", 0.0)),
            step=0.1,
            key=f"voyage_duration_{idx}",
            label_visibility="collapsed",
        )
        if col_action.button("－", key=f"remove_voyage_row_{idx}"):
            st.session_state["voyage_rows"].pop(idx)
            st.rerun()

    st.markdown(
        """
        <style>
        div[data-testid="stButton"] button[kind="secondary"] {
            font-size: 1.05rem;
            padding: 0.5rem 1rem;
            font-weight: 600;
        }
        .full-width-button {
            margin: 0 0.25rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="full-width-button">', unsafe_allow_html=True)
    if st.button("발전기 및 ESS 배터리 적정 용량 산정", key="size_generator_ess", use_container_width=True):
        main_df = st.session_state.get("main_df", pd.DataFrame())
        ela_meta = st.session_state.get("ela_meta", {})

        if main_df.empty:
            st.warning("ELA 파일을 먼저 업로드해주세요.")
            return

        consumer_col = ela_meta.get("consumer_col", "ELEC. CONSUMER")
        output_col = ela_meta.get("output_col", "OUTPUT(KW)")
        qty_col = ela_meta.get("qty_col", "Q'TY")
        working_col = ela_meta.get("working_col", "WORKING")
        modes = ela_meta.get("modes", [])

        source_input_col = "INPUT_USED" if "INPUT_USED" in main_df.columns else ela_meta.get("input_col", "INPUT(KW)")
        if source_input_col not in main_df.columns:
            st.warning("input load 컬럼을 찾을 수 없습니다.")
            return

        top3_df = main_df.copy()
        top3_df[source_input_col] = pd.to_numeric(top3_df[source_input_col], errors="coerce").fillna(0.0)
        top3_df = top3_df.nlargest(3, source_input_col)

        result_df = pd.DataFrame(
            {
                "electric consumer": top3_df[consumer_col].astype(str),
                "output": pd.to_numeric(top3_df[output_col], errors="coerce").fillna(0.0).round(2),
                "q'ty": pd.to_numeric(top3_df[qty_col], errors="coerce").fillna(0).astype(int),
                "working": pd.to_numeric(top3_df[working_col], errors="coerce").fillna(0).astype(int),
                "input load": top3_df[source_input_col].round(2),
            }
        )

        for mode in modes:
            cl_col = f"{mode}_CL"
            il_col = f"{mode}_IL"
            cl_values = pd.to_numeric(top3_df.get(cl_col, 0), errors="coerce").fillna(0.0)
            il_values = pd.to_numeric(top3_df.get(il_col, 0), errors="coerce").fillna(0.0)
            result_df[f"{mode} load"] = [f"C.L:{cl:.2f} / I.L:{il:.2f}" for cl, il in zip(cl_values, il_values)]

        result_df["권장 기동 방식"] = ""

        st.subheader("Top 3 개별 부하 (input load 기준)")
        st.dataframe(result_df, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.title("Power System Scenario Profile Tool")
    
    st.subheader("📂 ELA Upload")

    uploaded_file = st.file_uploader("Upload ELA Excel", type=["xlsx", "xls"])
    il_df = st.number_input(
        "I.L Diversity Factor",
        min_value=1.0,
        max_value=5.0,
        value=2.0,
        step=0.5,
        key="main_il_diversity_factor",
    )

    if uploaded_file is not None:
        try:
            _, main_df, _, meta, _, adapter_handoff_df = parse_ela_excel(uploaded_file, il_df=il_df)

            # 🔥 핵심: 세션에 저장
            st.session_state["adapter_handoff_df"] = adapter_handoff_df
            st.session_state["main_df"] = main_df
            st.session_state["ela_meta"] = meta

            st.success("ELA loaded successfully")

            # 확인용 (선택)
            display_df = adapter_handoff_df.drop(columns=["duration_hr"], errors="ignore")
            st.dataframe(display_df, use_container_width=True)

        except Exception as e:
            st.error(f"ELA parsing error: {e}")
    else:
        st.session_state["adapter_handoff_df"] = pd.DataFrame()
        st.info("ELA 파일 업로드 전에는 Scenario Load 값이 0으로 표시됩니다.")
    
    st.caption("Scenario-based load profile prototype")

    input_data = build_editable_input_data()

    try:
        scenario_df = build_scenario_dataframe(input_data)

    except Exception as exc:
        st.error(f"Calculation error: {exc}")
        st.stop()

    st.subheader("Load Profile")
    plot_load_profile_streamlit(scenario_df)
    available_scenarios = scenario_df["scenario"].astype(str).tolist() if "scenario" in scenario_df.columns else []
    render_voyage_scenario_planner(available_scenarios)


if __name__ == "__main__":
    main()