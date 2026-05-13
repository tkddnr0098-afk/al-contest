from __future__ import annotations

from copy import deepcopy
import re

import pandas as pd
import streamlit as st

from ela_read import parse_ela_excel
from adapters import build_input_data_from_dummy, build_input_data_from_ela_result
from calc_engine import build_scenario_dataframe
from config import DEFAULT_INPUT_DATA


st.set_page_config(page_title="Power System Scenario Profile Tool", layout="wide")


def build_generator_capacity_recommendation_df(scenario_df: pd.DataFrame) -> pd.DataFrame:
    if scenario_df is None or scenario_df.empty or "total_load_kw" not in scenario_df.columns:
        return pd.DataFrame()

    peak_row = scenario_df.loc[scenario_df["total_load_kw"].astype(float)
                               .idxmax()]
    peak_scenario = str(peak_row["scenario"])
    peak_total_load_kw = _safe_float(peak_row["total_load_kw"])

    targets = [75.0, 80.0, 85.0]
    rows = []
    for target_pct in targets:
        recommended_capacity_kw = peak_total_load_kw / (target_pct / 100.0) if target_pct else 0.0
        rows.append(
            {
                "peak_scenario": peak_scenario,
                "peak_total_load_kw": round(peak_total_load_kw, 2),
                "target_load_percent": target_pct,
                "recommended_generator_capacity_kw": round(recommended_capacity_kw, 2),
            }
        )

    return pd.DataFrame(rows)


def _classify_capacity_load_status(load_pct: float) -> str:
    if load_pct < 30.0:
        return "가능 (저부하 주의)"
    if load_pct < 75.0:
        return "가능"
    if load_pct <= 85.0:
        return "가능 (적정)"
    return "불가"


def build_generator_capacity_application_df(
    peak_total_load_kw: float,
    generator_capacity_kw: float,
    max_generators: int = 4,
) -> pd.DataFrame:
    rows = []
    for count in range(1, max_generators + 1):
        total_capacity_kw = generator_capacity_kw * count
        load_pct = (peak_total_load_kw / total_capacity_kw * 100.0) if total_capacity_kw > 0 else 0.0
        load_pct_int = int(round(load_pct))
        is_first_row = count == 1
        n_minus_one_capacity_kw = generator_capacity_kw * max(0, count - 1)
        n_minus_one_possible = peak_total_load_kw <= n_minus_one_capacity_kw
        if is_first_row:
            n_minus_one_status = _classify_capacity_load_status(load_pct_int)
        else:
            n_minus_one_status = _classify_capacity_load_status(load_pct_int) if n_minus_one_possible else "불가"

        operation_condition = "평상시 (1대)" if is_first_row else f"병렬운전 ({count}대)"
        label = "" if is_first_row else f"{count} X GENERATOR"

        rows.append(
            {
                "구분": label,
                "운전 조건": operation_condition,
                "사용 가능 용량 (LOAD %)": f"{total_capacity_kw:.1f} kW ({load_pct_int}%)",
                "N-1 가능 여부": n_minus_one_status,
            }
        )

    application_df = pd.DataFrame(rows)
    application_df.index = ["", 1, 2, 3]
    return application_df


def render_generator_capacity_application_table(application_df: pd.DataFrame) -> None:
    st.dataframe(application_df, use_container_width=True)


def render_generator_capacity_cards(recommendation_df: pd.DataFrame, selected_index: int, generator_count_text: str) -> int:
    st.markdown(
        """
        <style>
        .gen-cap-index {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        .gen-cap-card {
            border: 2px solid #cbd5e1;
            padding: 18px 12px 10px 12px;
            text-align: center;
            min-height: 120px;
            background: #ffffff;
        }
        .gen-cap-card.selected {
            border-color: #2563eb;
            background: #eff6ff;
        }
        .gen-cap-kw {
            font-size: 24px;
            font-weight: 800;
            margin-bottom: 12px;
        }
        .gen-cap-sub {
            font-size: 14px;
            margin-top: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(len(recommendation_df))
    new_selected_index = selected_index

    for idx, (_, row) in enumerate(recommendation_df.iterrows()):
        target_pct = int(round(_safe_float(row.get("target_load_percent"))))
        recommended_kw = _safe_float(row.get("recommended_generator_capacity_kw"))
        selected_class = " selected" if idx == selected_index else ""
        with cols[idx]:
            st.markdown(f'<div class="gen-cap-index">{idx + 1}.</div>', unsafe_allow_html=True)
            st.markdown(
                (
                    f'<div class="gen-cap-card{selected_class}">'
                    f'<div class="gen-cap-kw">{recommended_kw:.1f}kW</div>'
                    f'<div class="gen-cap-sub">LOAD PERCENT OF GEN. : {target_pct}%</div>'
                    f'</div>'
                ),
                unsafe_allow_html=True,
            )
            if st.button("적용", key=f"generator_capacity_option_{idx}", use_container_width=True):
                already_selected = st.session_state.get("selected_generator_capacity_option") == idx
                already_applied = st.session_state.get("generator_capacity_option_applied", False)
                new_selected_index = idx
                st.session_state["selected_generator_capacity_option"] = idx
                st.session_state["generator_capacity_option_applied"] = not (already_selected and already_applied)
                st.rerun()

    return new_selected_index


def _normalize_token(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"[^A-Z0-9가-힣]+", "", str(value).upper())


def _safe_float(value, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(numeric):
        return default
    return numeric


STARTING_PROFILES = [
    {
        "name": "원심펌프, 팬, 블로워",
        "initial_pct": 0.0,
        "stop_pct": 60.0,
        "motor_factor": 1.60,
        "keywords": ["PUMP", "P/P", "펌프", "FAN", "BLOWER", "VENT", "팬", "송풍기"],
    },
    {
        "name": "스크류펌프, 기어펌프",
        "initial_pct": 25.0,
        "stop_pct": 50.0,
        "motor_factor": 1.65,
        "keywords": ["SCREW PUMP", "SCREW", "스크류펌프", "스크류", "GEAR PUMP", "GEAR", "기어펌프", "기어"],
    },
    {
        "name": "압축기",
        "initial_pct": 50.0,
        "stop_pct": 40.0,
        "motor_factor": 1.70,
        "keywords": ["COMPRESSOR", "압축기", "AIR COMP"],
    },
    {
        "name": "윈치, 크레인, 컨베이어",
        "initial_pct": 75.0,
        "stop_pct": 25.0,
        "motor_factor": 1.80,
        "keywords": ["WINCH", "WINDLASS", "CRANE", "CONVEYOR", "윈치", "크레인", "컨베이어"],
    },
    {
        "name": "프로펠러 직결, 고관성 부하",
        "initial_pct": 75.0,
        "stop_pct": 25.0,
        "motor_factor": 1.80,
        "keywords": ["PROPULSION", "PROPELLER", "THRUSTER", "추진", "프로펠러", "쓰러스터", "THRUST"],
    },
    {
        "name": "해당 없음",
        "initial_pct": -1.0,
        "stop_pct": None,
        "motor_factor": None,
        "keywords": ["HEATER", "PRE-HEATER", "PRE HEATER", "LIGHT", "LIGHTING", "CHARGER", "온수기", "조명", "충전기", "히터"],
    },
]


def classify_starting_profile(electric_consumer: str) -> dict | None:
    normalized_name = _normalize_token(electric_consumer)
    if not normalized_name:
        return None

    matches = []
    for profile in STARTING_PROFILES:
        if any(_normalize_token(keyword) in normalized_name for keyword in profile["keywords"]):
            matches.append(profile)

    if not matches:
        return None

    matches.sort(key=lambda item: item["initial_pct"], reverse=True)
    return matches[0]


def build_scenario_load_percent_map(scenario_df: pd.DataFrame, generator_capacity_kw: float) -> dict[str, float]:
    if generator_capacity_kw <= 0:
        return {}

    scenario_load_pct = {}
    for _, row in scenario_df.iterrows():
        scenario_name = str(row.get("scenario", ""))
        total_load_kw = _safe_float(row.get("total_load_kw"))
        scenario_load_pct[_normalize_token(scenario_name)] = (total_load_kw / generator_capacity_kw) * 100.0
    return scenario_load_pct


def find_peak_mode_for_row(row: pd.Series, modes: list[str], il_df: float) -> str:
    best_mode = ""
    best_load = 0.0

    for mode in modes:
        cl_value = _safe_float(row.get(f"{mode}_CL"))
        il_applied_value = row.get(f"{mode}_IL_APPLIED")
        if pd.isna(il_applied_value):
            il_applied_value = _safe_float(row.get(f"{mode}_IL")) / float(il_df) if il_df else _safe_float(row.get(f"{mode}_IL"))
        else:
            il_applied_value = _safe_float(il_applied_value)

        mode_load = cl_value + il_applied_value
        if mode_load > best_load:
            best_load = mode_load
            best_mode = mode

    return best_mode


def recommend_starting_method(
    electric_consumer: str,
    motor_output_kw: float,
    scenario_name: str,
    scenario_load_pct_map: dict[str, float],
    generator_capacity_kw: float,
) -> str:
    profile = classify_starting_profile(electric_consumer)
    if profile is None:
        return "검토 필요"

    if profile["name"] == "해당 없음":
        return "해당 없음"

    load_percent = scenario_load_pct_map.get(_normalize_token(scenario_name))
    if load_percent is None:
        return "검토 필요"

    initial_pct = float(profile["initial_pct"])

    if motor_output_kw * float(profile["motor_factor"]) > generator_capacity_kw:
        return "Auto Transformer"

    if initial_pct in {0.0, 25.0}:
        if motor_output_kw <= generator_capacity_kw * 0.10:
            return "직입기동 (DOL)"
        return "Open Y-Δ"

    delta = load_percent - float(profile["stop_pct"])
    if delta <= 0:
        return "Open Y-Δ (DOL 비권장)"
    if delta <= 10:
        return "Open Y-Δ"
    if delta <= 20:
        return "Auto Transformer"
    return "Auto Transformer (검토 필요)"

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


def render_voyage_scenario_planner(
    available_scenarios: list[str],
    scenario_df: pd.DataFrame,
    input_data: dict,
) -> None:
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
    if st.button("선종별 duration_hr", key="vessel_type_duration_hr", use_container_width=True):
        st.session_state["show_vessel_duration_buttons"] = not st.session_state.get("show_vessel_duration_buttons", False)

    if st.session_state.get("show_vessel_duration_buttons", False):
        vessel_cols = st.columns(10)
        for i, vessel_col in enumerate(vessel_cols):
            vessel_col.button("\u200b", key=f"vessel_duration_btn_{i}", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)
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
    header_mode, header_duration, header_running_gen, _ = st.columns([2, 1, 1, 0.5])
    header_mode.markdown("**Mode**")
    header_duration.markdown("**duration_hr**")
    header_running_gen.markdown("**running_gen**")

    default_mode_options = ["NORMAL", "PORT_IN_OUT", "WORKING", "HARBOUR"]
    mode_options = [str(mode) for mode in available_scenarios if str(mode).strip()]
    if not mode_options:
        mode_options = default_mode_options
    mode_options = [str(mode) for mode in available_scenarios if str(mode).strip()]
    if not mode_options:
        mode_options = default_mode_options
    next_voyage_row_id = int(st.session_state.get("next_voyage_row_id", 0))
    if "voyage_rows" not in st.session_state:
        st.session_state["voyage_rows"] = [
            {"id": idx, "mode": mode_options[idx % len(mode_options)], "duration_hr": 0.0, "running_gen": 0}
            for idx in range(4)
        ]
        next_voyage_row_id = 4
    for row in st.session_state["voyage_rows"]:
        if "id" not in row:
            row["id"] = next_voyage_row_id
            next_voyage_row_id += 1
    st.session_state["next_voyage_row_id"] = next_voyage_row_id
    
    if st.button("＋ 행 추가", key="add_voyage_row"):
        row_id = int(st.session_state.get("next_voyage_row_id", 0))
        st.session_state["voyage_rows"].append({"id": row_id, "mode": mode_options[0], "duration_hr": 0.0, "running_gen": 0})
        st.session_state["next_voyage_row_id"] = row_id + 1

    remove_row_id = None
    for idx, row in enumerate(st.session_state["voyage_rows"]):
        row_id = int(row.get("id", idx))
        col_mode, col_duration, col_running_gen, col_action = st.columns([2, 1, 1, 0.5])
        current_mode = str(row.get("mode", mode_options[0]))
        select_options = mode_options if current_mode in mode_options else [*mode_options, current_mode]
        current_mode_index = select_options.index(current_mode) if current_mode in select_options else 0
        row["mode"] = col_mode.selectbox(
            "Mode",
            options=select_options,
            index=current_mode_index,
            key=f"voyage_mode_{row_id}",
            label_visibility="collapsed",
        )
        row["duration_hr"] = col_duration.number_input(
            "duration_hr",
            min_value=0.0,
            value=float(row.get("duration_hr", 0.0)),
            step=0.1,
            key=f"voyage_duration_{row_id}",
            label_visibility="collapsed",
        )
        row["running_gen"] = int(col_running_gen.number_input(
            "running_gen",
            min_value=0,
            value=int(row.get("running_gen", 0)),
            step=1,
            key=f"voyage_running_gen_{row_id}",
            label_visibility="collapsed",
        ))
        if col_action.button("－", key=f"remove_voyage_row_{row_id}"):
            remove_row_id = row_id

    if remove_row_id is not None:
        st.session_state["voyage_rows"] = [row for row in st.session_state["voyage_rows"] if int(row.get("id", -1)) != remove_row_id]
        st.rerun()
        
    st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)
    if st.button("발전기 및 ESS 배터리 적정 용량 산정", key="size_generator_ess", use_container_width=True):
        st.session_state["show_generator_sizing"] = True

    if st.session_state.get("show_generator_sizing", False):
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
        il_df = float(ela_meta.get("il_df", 1.0))
        generator_count_text = ""

        source_input_col = "INPUT_USED" if "INPUT_USED" in main_df.columns else ela_meta.get("input_col", "INPUT(KW)")
        if source_input_col not in main_df.columns:
            st.warning("input load 컬럼을 찾을 수 없습니다.")
            return

        recommendation_df = build_generator_capacity_recommendation_df(scenario_df)
        if recommendation_df.empty:
            st.warning("발전기 용량 추천을 계산할 수 없습니다.")
            return

        selected_option = int(st.session_state.get("selected_generator_capacity_option", 0))
        if selected_option < 0 or selected_option >= len(recommendation_df):
            selected_option = 0
            st.session_state["selected_generator_capacity_option"] = selected_option

        selected_row = recommendation_df.iloc[selected_option]
        generator_capacity_kw = _safe_float(selected_row["recommended_generator_capacity_kw"])
        scenario_load_pct_map = build_scenario_load_percent_map(scenario_df, generator_capacity_kw)

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

        def format_mode_load(cl: float, il: float) -> str:
            cl_text = f"C.L : {cl:.2f}" if cl != 0 else ""
            il_text = f"I.L : {il:.2f}" if il != 0 else ""
            if cl_text and il_text:
                return f"{cl_text} / {il_text}"
            if cl_text:
                return cl_text
            if il_text:
                return il_text
            return "-"

        for mode in modes:
            cl_col = f"{mode}_CL"
            il_col = f"{mode}_IL"
            cl_values = pd.to_numeric(top3_df.get(cl_col, 0), errors="coerce").fillna(0.0)
            il_values = pd.to_numeric(top3_df.get(il_col, 0), errors="coerce").fillna(0.0)
            result_df[f"{mode} load"] = [format_mode_load(cl, il) for cl, il in zip(cl_values, il_values)]

        recommendations = []
        for _, row in top3_df.iterrows():
            peak_mode = find_peak_mode_for_row(row, modes, il_df)
            recommendations.append(
                recommend_starting_method(
                    electric_consumer=str(row.get(consumer_col, "")),
                    motor_output_kw=_safe_float(row.get(output_col)),
                    scenario_name=peak_mode,
                    scenario_load_pct_map=scenario_load_pct_map,
                    generator_capacity_kw=generator_capacity_kw,
                )
            )

        result_df["권장 기동 방식"] = recommendations

        st.subheader("Top 3 개별 부하 (input load 기준)")
        st.dataframe(result_df, use_container_width=True)
        st.subheader("발전기 용량 추천")
        render_generator_capacity_cards(recommendation_df, selected_option, generator_count_text)

        if st.session_state.get("generator_capacity_option_applied", False):
            st.markdown("**발전기 대수별 비교**")
            peak_total_load_kw = _safe_float(selected_row["peak_total_load_kw"])
            application_df = build_generator_capacity_application_df(
                peak_total_load_kw=peak_total_load_kw,
                generator_capacity_kw=generator_capacity_kw,
                max_generators=4,
            )
            render_generator_capacity_application_table(application_df)
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.title("Power System Scenario Profile Tool")
    
    st.subheader("📂 ELA Upload")

    uploaded_file = st.file_uploader("Upload ELA Excel", type=["xlsx", "xls"])

    st.caption("Scenario-based load profile prototype")
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
            numeric_cols = display_df.select_dtypes(include="number").columns
            display_df[numeric_cols] = display_df[numeric_cols].round(2)
            st.dataframe(display_df, use_container_width=True)

        except Exception as e:
            st.error(f"ELA parsing error: {e}")
    else:
        st.session_state["adapter_handoff_df"] = pd.DataFrame()
        st.session_state["show_generator_sizing"] = False
        st.info("ELA 파일 업로드 전에는 Scenario Load 값이 0으로 표시됩니다.")

    input_data = build_editable_input_data()

    try:
        scenario_df = build_scenario_dataframe(input_data)

    except Exception as exc:
        st.error(f"Calculation error: {exc}")
        st.stop()

    available_scenarios = scenario_df["scenario"].astype(str).tolist() if "scenario" in scenario_df.columns else []
    render_voyage_scenario_planner(available_scenarios, scenario_df, input_data)


if __name__ == "__main__":
    main()