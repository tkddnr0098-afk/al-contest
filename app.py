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
    y = scenario_df["total_load_kw"]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(x, y, color="#1f77b4")
    ax.bar_label(bars, labels=[f"{value:.1f}" for value in y], padding=3, fontsize=9)
    ax.set_title("Load Profile")
    ax.set_ylabel("kW")
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
    generator_enabled = not is_pure_electric
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
    ess_enabled = not is_conventional
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


if __name__ == "__main__":
    main()