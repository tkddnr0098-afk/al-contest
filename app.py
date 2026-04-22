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

    total_load = scenario_df["total_load_kw"].astype(float)
    ax.plot(x, total_load, marker="o", color="black", linewidth=1.5, label="Total Load")
    for idx, value in enumerate(total_load):
        ax.text(idx, value + 0.5, f"{value:.1f}", ha="center", va="bottom", fontsize=9)

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

    if st.button("발전기 및 ESS 배터리 적정 용량 산정", key="size_generator_ess"):
        st.info("향후 계산 로직 및 그래프를 이 영역에 추가할 예정입니다.")


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
            _, _, _, _, _, adapter_handoff_df = parse_ela_excel(uploaded_file, il_df=il_df)

            # 🔥 핵심: 세션에 저장
            st.session_state["adapter_handoff_df"] = adapter_handoff_df

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

    available_scenarios = scenario_df["scenario"].astype(str).tolist() if "scenario" in scenario_df.columns else []
    render_voyage_scenario_planner(available_scenarios)

    st.subheader("Load Profile")
    plot_load_profile_streamlit(scenario_df)


if __name__ == "__main__":
    main()