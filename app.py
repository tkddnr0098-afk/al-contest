from __future__ import annotations

from copy import deepcopy

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from ela_read import parse_ela_excel
from adapters import build_input_data_from_dummy, build_input_data_from_ela_result
from calc_engine import (
    build_generator_loading_dataframe,
    build_scenario_dataframe,
    build_summary_metrics,
)
from config import DEFAULT_INPUT_DATA


st.set_page_config(page_title="Power System Scenario Profile Tool", layout="wide")


def plot_load_profile_streamlit(scenario_df: pd.DataFrame) -> None:
    x = scenario_df["scenario"]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.stackplot(
        x,
        scenario_df["continuous_load_kw"],
        scenario_df["intermittent_load_kw"],
        scenario_df["aux_load_kw"],
        scenario_df["propulsion_load_kw"],
        labels=["Continuous", "Intermittent", "Aux", "Propulsion"],
    )
    ax.plot(x, scenario_df["total_load_kw"], marker="o", label="Total Load")
    ax.set_title("Scenario Load Profile")
    ax.set_ylabel("kW")
    ax.legend()
    fig.tight_layout()
    st.pyplot(fig)


def plot_generator_loading_streamlit(
    generator_loading_df: pd.DataFrame,
    target_lf_pct: float = 80.0,
    absolute_max_pct: float = 100.0,
) -> None:
    if generator_loading_df.empty:
        st.info("Generator loading data is empty.")
        return

    pivot_df = (
        generator_loading_df
        .pivot(index="scenario", columns="generator", values="loading_pct")
        .fillna(0.0)
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    pivot_df.plot(kind="bar", ax=ax)
    ax.axhline(target_lf_pct, linestyle="--", label=f"Target LF {target_lf_pct:.0f}%")
    ax.axhline(absolute_max_pct, linestyle="--", label=f"Absolute Max {absolute_max_pct:.0f}%")
    ax.set_title("Generator Loading Profile")
    ax.set_ylabel("Load Factor (%)")
    ax.legend()
    fig.tight_layout()
    st.pyplot(fig)


def plot_soc_profile_streamlit(scenario_df: pd.DataFrame) -> None:
    if "soc_start_pct" not in scenario_df.columns or "soc_end_pct" not in scenario_df.columns:
        st.info("SOC data not found.")
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(scenario_df["scenario"], scenario_df["soc_start_pct"], marker="o", label="SOC Start")
    ax.plot(scenario_df["scenario"], scenario_df["soc_end_pct"], marker="o", label="SOC End")
    ax.set_title("ESS SOC Profile")
    ax.set_ylabel("SOC (%)")
    ax.set_ylim(0, 100)
    ax.legend()
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

    # number_input/selectbox 위젯은 key가 같으면 이전 상태를 유지하므로,
    # ELA 로드 상태가 바뀌거나 파일이 갱신되면 시나리오 위젯 상태를 강제로 동기화한다.
    scenario_state_signature = "ela_empty"
    if ela_loaded:
        value_signature = int(pd.util.hash_pandas_object(ela_df, index=True).sum())
        scenario_state_signature = f"ela_loaded:{value_signature}"
    if st.session_state.get("scenario_widget_signature") != scenario_state_signature:
        for i, scenario in enumerate(input_data["scenarios"]):
            st.session_state[f"duration_{i}"] = float(scenario.get("duration_hr", 1.0))
            st.session_state[f"cont_{i}"] = float(scenario.get("continuous_load_kw", 0.0))
            st.session_state[f"inter_{i}"] = float(scenario.get("intermittent_load_kw", 0.0))
            st.session_state[f"aux_{i}"] = float(
                scenario.get("deck_machinery_load_kw", scenario.get("aux_load_kw", 0.0))
            )
            st.session_state[f"prop_{i}"] = float(scenario.get("propulsion_load_kw", 0.0))
            st.session_state[f"ess_mode_{i}"] = str(scenario.get("ess_mode", "idle"))
            st.session_state[f"ess_power_{i}"] = float(scenario.get("ess_power_kw", 0.0))
        st.session_state["scenario_widget_signature"] = scenario_state_signature

    st.sidebar.header("System Settings")

    system_options = ["conventional", "diesel_electric", "hybrid", "pure_electric"]
    input_data["system_type"] = st.sidebar.selectbox(
        "System Type",
        system_options,
        index=system_options.index(input_data["system_type"]),
    )

    is_conventional = input_data["system_type"] == "conventional"
    is_pure_electric = input_data["system_type"] == "pure_electric"

    st.sidebar.subheader("Generator")

    if is_pure_electric:
        generator_enabled = st.sidebar.checkbox(
            "Generator Enabled",
            value=False,
            disabled=True,
        )
    else:
        generator_enabled = st.sidebar.checkbox(
            "Generator Enabled",
            value=True,
        )

    input_data["generator_spec"]["enabled"] = generator_enabled

    input_data["generator_spec"]["unit_rating_kw"] = st.sidebar.number_input(
        "Generator Unit Rating (kW)",
        min_value=100.0,
        value=float(input_data["generator_spec"]["unit_rating_kw"]),
        step=50.0,
        disabled=not generator_enabled,
    )
    input_data["generator_spec"]["count_installed"] = st.sidebar.number_input(
        "Installed Generator Count",
        min_value=1,
        value=int(input_data["generator_spec"]["count_installed"]),
        step=1,
        disabled=not generator_enabled,
    )
    input_data["generator_spec"]["target_load_factor"] = st.sidebar.slider(
        "Target Load Factor",
        min_value=0.30,
        max_value=1.00,
        value=float(input_data["generator_spec"]["target_load_factor"]),
        step=0.01,
        disabled=not generator_enabled,
    )

    st.sidebar.subheader("ESS")

    if is_conventional:
        input_data["ess_spec"]["enabled"] = False
        ess_enabled = st.sidebar.checkbox(
            "ESS Enabled",
            value=False,
            disabled=True,
        )
    else:
        ess_enabled = st.sidebar.checkbox(
            "ESS Enabled",
            value=bool(input_data["ess_spec"]["enabled"]),
        )
        input_data["ess_spec"]["enabled"] = ess_enabled

    input_data["ess_spec"]["capacity_kwh"] = st.sidebar.number_input(
        "ESS Capacity (kWh)",
        min_value=100.0,
        value=float(input_data["ess_spec"]["capacity_kwh"]),
        step=100.0,
        disabled=not ess_enabled or is_conventional,
    )
    input_data["ess_spec"]["max_charge_kw"] = st.sidebar.number_input(
        "ESS Max Charge (kW)",
        min_value=0.0,
        value=float(input_data["ess_spec"]["max_charge_kw"]),
        step=50.0,
        disabled=not ess_enabled or is_conventional,
    )
    input_data["ess_spec"]["max_discharge_kw"] = st.sidebar.number_input(
        "ESS Max Discharge (kW)",
        min_value=0.0,
        value=float(input_data["ess_spec"]["max_discharge_kw"]),
        step=50.0,
        disabled=not ess_enabled or is_conventional,
    )
    input_data["ess_spec"]["soc_init"] = st.sidebar.slider(
        "ESS Initial SOC",
        min_value=0.0,
        max_value=1.0,
        value=float(input_data["ess_spec"]["soc_init"]),
        step=0.01,
        disabled=not ess_enabled or is_conventional,
    )
    input_data["ess_spec"]["soc_min"] = st.sidebar.slider(
        "ESS Min SOC",
        min_value=0.0,
        max_value=1.0,
        value=float(input_data["ess_spec"]["soc_min"]),
        step=0.01,
        disabled=not ess_enabled or is_conventional,
    )
    input_data["ess_spec"]["soc_max"] = st.sidebar.slider(
        "ESS Max SOC",
        min_value=0.0,
        max_value=1.0,
        value=float(input_data["ess_spec"]["soc_max"]),
        step=0.01,
        disabled=not ess_enabled or is_conventional,
    )

    st.sidebar.header("Scenario Settings")

    for i, scenario in enumerate(input_data["scenarios"]):
        exp = st.sidebar.expander(f"Scenario {i+1} - {scenario['name']}", expanded=False)

        scenario["duration_hr"] = exp.number_input(
            "Duration (hr)",
            min_value=0.1,
            value=float(scenario["duration_hr"]),
            step=0.1,
            key=f"duration_{i}",
        )

        exp.markdown("**Hotel Load (kW)**")
        scenario["continuous_load_kw"] = exp.number_input(
            "Continuous Load (kW)",
            min_value=0.0,
            value=float(scenario.get("continuous_load_kw", 0.0)),
            step=10.0,
            key=f"cont_{i}",
            disabled=not ela_loaded,
        )
        scenario["intermittent_load_kw"] = exp.number_input(
            "Intermittent Load (kW)",
            min_value=0.0,
            value=float(scenario.get("intermittent_load_kw", 0.0)),
            step=10.0,
            key=f"inter_{i}",
            disabled=not ela_loaded,
        )

        intermittent_raw = float(scenario.get("intermittent_load_raw_kw", scenario["intermittent_load_kw"]))
        diversity_factor = float(scenario.get("diversity_factor", 1.0))
        hotel_load_kw = float(scenario.get("hotel_load_kw", scenario["continuous_load_kw"] + scenario["intermittent_load_kw"]))
        deck_machinery_load_kw = float(scenario.get("deck_machinery_load_kw", scenario.get("aux_load_kw", 0.0)))

        exp.markdown(f"Intermittent Raw: **{intermittent_raw:.1f} kW**")
        exp.markdown(f"Diversity Factor: **{diversity_factor:.2f}**")
        exp.markdown(f"Hotel Load: **{hotel_load_kw:.1f} kW**")
        exp.markdown(f"Deck Machinery Load: **{deck_machinery_load_kw:.1f} kW**")
        exp.markdown(
            f"Hotel Total: **{scenario['continuous_load_kw'] + scenario['intermittent_load_kw']:.1f} kW**"
        )

        scenario["deck_machinery_load_kw"] = exp.number_input(
            "Deck Mach. Load (kW)",
            min_value=0.0,
            value=deck_machinery_load_kw,
            step=10.0,
            key=f"aux_{i}",
            disabled=not ela_loaded,
        )
        scenario["aux_load_kw"] = scenario["deck_machinery_load_kw"]
        scenario["propulsion_load_kw"] = exp.number_input(
            "Propulsion Load (kW)",
            min_value=0.0,
            value=float(scenario.get("propulsion_load_kw", 0.0)),
            step=10.0,
            key=f"prop_{i}",
            disabled=not ela_loaded,
        )

        ess_mode_options = ["idle", "charge", "discharge"]
        current_mode = scenario.get("ess_mode", "idle")
        if current_mode not in ess_mode_options:
            current_mode = "idle"

        scenario["ess_mode"] = exp.selectbox(
            "ESS Mode",
            ess_mode_options,
            index=ess_mode_options.index(current_mode),
            key=f"ess_mode_{i}",
            disabled=not ess_enabled or is_conventional,
        )
        scenario["ess_power_kw"] = exp.number_input(
            "ESS Power (kW)",
            min_value=0.0,
            value=float(scenario.get("ess_power_kw", 0.0)),
            step=10.0,
            key=f"ess_power_{i}",
            disabled=not ess_enabled or is_conventional,
        )

    return input_data


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
            st.dataframe(adapter_handoff_df, use_container_width=True)

        except Exception as e:
            st.error(f"ELA parsing error: {e}")
    else:
        st.session_state["adapter_handoff_df"] = pd.DataFrame()
        st.info("ELA 파일 업로드 전에는 Scenario Load 값이 0으로 표시됩니다.")
    
    st.caption("Scenario-based load, generator loading, and ESS SOC prototype")

    input_data = build_editable_input_data()

    try:
        scenario_df = build_scenario_dataframe(input_data)

        generator_enabled = input_data["generator_spec"].get("enabled", True)

        if generator_enabled:
            generator_loading_df = build_generator_loading_dataframe(
                scenario_df=scenario_df,
                unit_rating_kw=float(input_data["generator_spec"]["unit_rating_kw"]),
            )
        else:
            generator_loading_df = pd.DataFrame()

        summary = build_summary_metrics(input_data, scenario_df)
        
    except Exception as exc:
        st.error(f"Calculation error: {exc}")
        st.stop()

    st.subheader("Summary Metrics")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("System Type", summary["system_type"])
    c2.metric("Scenario Count", summary["scenario_count"])
    c3.metric("Max Total Load (kW)", f"{summary['max_total_load_kw']:.1f}")
    c4.metric("Avg Gen LF (%)", f"{summary['avg_gen_loading_pct']:.1f}")
    c5.metric("Max Required DG", f"{summary['max_required_gen_count']}")

    st.subheader("Scenario Data")
    st.dataframe(scenario_df, use_container_width=True)

    st.subheader("Load Profile")
    plot_load_profile_streamlit(scenario_df)

    if input_data["generator_spec"].get("enabled", True):
        st.subheader("Generator Loading Profile")
        plot_generator_loading_streamlit(
            generator_loading_df,
            target_lf_pct=float(input_data["generator_spec"]["target_load_factor"]) * 100.0,
            absolute_max_pct=float(input_data["generator_spec"]["absolute_max_lf"]) * 100.0,
        )

    if input_data["system_type"] in {"hybrid", "pure_electric"} and input_data["ess_spec"]["enabled"]:
        st.subheader("ESS SOC Profile")
        plot_soc_profile_streamlit(scenario_df)


if __name__ == "__main__":
    main()