import streamlit as st
import numpy as np
import pandas as pd
import re


# =========================================================
# Helpers
# =========================================================
def classify_load_category(name: str) -> str:
    """
    부하명을 기준으로 category 분류
    - propulsion / 추진 포함 -> propulsion
    - crane / 크레인 / winch / 윈치 / windlass / 윈드라스 포함 -> deck_machinery
    - 나머지 -> hotel
    """
    if pd.isna(name):
        return "hotel"

    text = str(name).strip().lower()

    propulsion_keywords = ["propulsion", "추진"]
    deck_machinery_keywords = ["crane", "크레인", "winch", "윈치", "windlass", "윈드라스"]

    if any(k in text for k in propulsion_keywords):
        return "propulsion"
    if any(k in text for k in deck_machinery_keywords):
        return "deck_machinery"
    return "hotel"


def build_mode_summary(df: pd.DataFrame, modes: list[str], il_df: float) -> pd.DataFrame:
    """
    mode별 CL / IL(raw) / IL(applied) / Total 집계 테이블 생성
    """
    rows = []
    for mode in modes:
        cl_sum = float(df.get(f"{mode}_CL", pd.Series(dtype=float)).fillna(0).sum())
        il_raw_sum = float(df.get(f"{mode}_IL", pd.Series(dtype=float)).fillna(0).sum())
        il_applied_sum = il_raw_sum / il_df if il_df else il_raw_sum
        total_sum = float(df.get(f"{mode}_TOTAL", pd.Series(dtype=float)).fillna(0).sum())

        rows.append(
            {
                "Mode": mode,
                "Continuous Load (kW)": cl_sum,
                "Intermittent Load Raw (kW)": il_raw_sum,
                "Div. Factor": il_df,
                "Intermittent Load Applied (kW)": il_applied_sum,
                "Total Load (kW)": total_sum,
            }
        )

    summary_df = pd.DataFrame(rows)
    numeric_cols = [
        "Continuous Load (kW)",
        "Intermittent Load Raw (kW)",
        "Div. Factor",
        "Intermittent Load Applied (kW)",
        "Total Load (kW)",
    ]
    for col in numeric_cols:
        if col in summary_df.columns:
            summary_df[col] = pd.to_numeric(summary_df[col], errors="coerce").round(2)
    return summary_df


def build_step1_checklist() -> pd.DataFrame:
    rows = [
        {
            "Step": 1,
            "Task": "표준 반환 구조 고정",
            "Detail": "parse_ela_excel() 반환값을 result / df / candidates / meta / mode_summary_df 로 고정",
            "Status": "진행중",
            "Output": "고정된 함수 반환 계약",
        },
        {
            "Step": 2,
            "Task": "Mode summary 컬럼 고정",
            "Detail": "scenario, continuous_load_kw, intermittent_load_raw_kw, diversity_factor, intermittent_load_kw, hotel_load_kw, deck_machinery_load_kw, propulsion_load_kw, total_load_kw, duration_hr 컬럼 정의",
            "Status": "진행중",
            "Output": "adapter 전달용 표준 summary 포맷",
        },
        {
            "Step": 3,
            "Task": "부하 분류 로직 고정",
            "Detail": "부하명을 기준으로 propulsion / deck_machinery / hotel 분류",
            "Status": "완료",
            "Output": "LOAD_CATEGORY 컬럼",
        },
        {
            "Step": 4,
            "Task": "Mode별 계산 로직 고정",
            "Detail": "CL, IL Raw, IL Applied, Total 계산 구조를 유지하고 summary에 반영",
            "Status": "완료",
            "Output": "mode별 집계값",
        },
        {
            "Step": 5,
            "Task": "adapter handoff 미리보기",
            "Detail": "adapters.py 로 넘길 컬럼과 기본값을 표로 확인",
            "Status": "진행중",
            "Output": "handoff preview table",
        },
    ]
    return pd.DataFrame(rows)


def build_adapter_handoff_table(df: pd.DataFrame, modes: list[str], il_df: float, default_duration_hr: float = 1.0) -> pd.DataFrame:
    rows = []
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "scenario",
            "continuous_load_kw",
            "intermittent_load_raw_kw",
            "diversity_factor",
            "intermittent_load_kw",
            "hotel_load_kw",
            "deck_machinery_load_kw",
            "propulsion_load_kw",
            "total_load_kw",
            "duration_hr",
        ])

    for mode in modes:
        continuous_kw = float(df.get(f"{mode}_CL", pd.Series(dtype=float)).fillna(0).sum())
        intermittent_raw_kw = float(df.get(f"{mode}_IL", pd.Series(dtype=float)).fillna(0).sum())
        intermittent_kw = float(df.get(f"{mode}_IL_APPLIED", pd.Series(dtype=float)).fillna(0).sum())
        total_kw = float(df.get(f"{mode}_TOTAL", pd.Series(dtype=float)).fillna(0).sum())

        propulsion_kw = float(
            df.loc[df["LOAD_CATEGORY"] == "propulsion", f"{mode}_TOTAL"].fillna(0).sum()
        ) if "LOAD_CATEGORY" in df.columns and f"{mode}_TOTAL" in df.columns else 0.0

        deck_machinery_kw = float(
            df.loc[df["LOAD_CATEGORY"] == "deck_machinery", f"{mode}_TOTAL"].fillna(0).sum()
        ) if "LOAD_CATEGORY" in df.columns and f"{mode}_TOTAL" in df.columns else 0.0

        hotel_kw = float(
            df.loc[df["LOAD_CATEGORY"] == "hotel", f"{mode}_TOTAL"].fillna(0).sum()
        ) if "LOAD_CATEGORY" in df.columns and f"{mode}_TOTAL" in df.columns else 0.0

        rows.append({
            "scenario": mode,
            "continuous_load_kw": round(continuous_kw, 2),
            "intermittent_load_raw_kw": round(intermittent_raw_kw, 2),
            "diversity_factor": round(float(il_df), 2),
            "intermittent_load_kw": round(intermittent_kw, 2),
            "hotel_load_kw": round(hotel_kw, 2),
            "deck_machinery_load_kw": round(deck_machinery_kw, 2),
            "propulsion_load_kw": round(propulsion_kw, 2),
            "total_load_kw": round(total_kw, 2),
            "duration_hr": round(float(default_duration_hr), 2),
        })

    return pd.DataFrame(rows)


# =========================================================
# ELA Parsing Helpers
# =========================================================
def _clean_text(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    if text.upper().startswith("UNNAMED:") or text.upper() == "NAN":
        return ""
    return text


def _upper_text(value) -> str:
    return _clean_text(value).upper()


def _normalize_mode_name(value) -> str:
    text = _upper_text(value)
    if not text:
        return ""

    text = text.replace("FITGTING", "FIGHTING")
    text = text.replace("FIRE FITGTING", "FIRE FIGHTING")
    text = text.replace("HARBOR", "HARBOUR")
    text = text.replace("ARR./PORT", "ARR_PORT")
    text = text.replace("&", " ")
    text = text.replace("/", " ")
    text = re.sub(r"\bSERVICE\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" ", "_")
    return text


def _normalize_subheader(value) -> str:
    text = _upper_text(value)
    text = text.replace(" ", "")
    if not text:
        return ""
    if text in {"%", "L.F", "LF"}:
        return "%"
    if "C.L" in text or text.startswith("CL"):
        return "C.L"
    if "I.L" in text or text.startswith("IL"):
        return "I.L"
    return ""


def _find_target_sheet(sheet_names: list[str]) -> str | None:
    ranked = []
    for idx, sheet in enumerate(sheet_names):
        s = sheet.lower().strip()
        score = -1
        if s == "anal":
            score = 100
        elif "load analysis" in s:
            score = 90
        elif "anal" in s:
            score = 80
        elif "analysis" in s:
            score = 70
        if score >= 0:
            ranked.append((score, idx, sheet))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    return ranked[0][2]


def _find_header_start(raw_df: pd.DataFrame) -> int:
    search_rows = min(len(raw_df), 15)
    for i in range(search_rows):
        row_vals = [_upper_text(v) for v in raw_df.iloc[i].tolist()]
        row_text = " | ".join(v for v in row_vals if v)
        row_compact = row_text.replace(" ", "")
        if "ELECTRICCONSUMER" in row_compact and "OUTPUT" in row_compact and "WORKING" in row_compact:
            return i
    raise ValueError("헤더 시작 행(ELECTRIC CONSUMER/OUTPUT/WORKING 포함)을 찾지 못했습니다.")


def _build_columns(raw_df: pd.DataFrame, header_row: int):
    row1 = raw_df.iloc[header_row]
    row2 = raw_df.iloc[header_row + 1] if header_row + 1 < len(raw_df) else pd.Series(dtype=object)
    row3 = raw_df.iloc[header_row + 2] if header_row + 2 < len(raw_df) else pd.Series(dtype=object)

    columns = []
    modes = []
    mode_cols = {}
    cl_cols = {}
    il_cols = {}

    working_idx = None
    pt_idx = None

    for col_idx in range(raw_df.shape[1]):
        h1 = _upper_text(row1.iloc[col_idx])
        h1_compact = h1.replace(" ", "")
        if working_idx is None and "WORK" in h1_compact:
            working_idx = col_idx
        if pt_idx is None and h1_compact == "PT":
            pt_idx = col_idx

    current_mode = ""

    for col_idx in range(raw_df.shape[1]):
        h1 = _upper_text(row1.iloc[col_idx])
        h2 = _upper_text(row2.iloc[col_idx])
        h3 = _upper_text(row3.iloc[col_idx])
        h1_compact = h1.replace(" ", "")

        name = ""
        if "ELECTRICCONSUMER" in h1_compact:
            name = "ELEC. CONSUMER"
        elif "OUTPUT" in h1_compact:
            name = "OUTPUT(KW)"
        elif "INPUT" in h1_compact:
            name = "INPUT(KW)"
        elif "Q" in h1_compact and "TY" in h1_compact:
            name = "Q'TY"
        elif "WORK" in h1_compact:
            name = "WORKING"
        elif h1_compact == "PT":
            name = "PT"
        elif working_idx is not None and col_idx > working_idx and (pt_idx is None or col_idx < pt_idx):
            mode = _normalize_mode_name(h2)
            sub = _normalize_subheader(h3)

            # mode명이 첫 열에만 있고 옆 C.L / I.L 셀은 비어 있는 경우가 많으므로
            # 직전 mode를 옆 열들에 이어서 적용한다.
            if mode:
                current_mode = mode
            else:
                mode = current_mode

            if mode and sub:
                name = f"{mode}_{sub}"
                if mode not in modes:
                    modes.append(mode)
                if sub == "%":
                    mode_cols[mode] = name
                elif sub == "C.L":
                    cl_cols[mode] = name
                elif sub == "I.L":
                    il_cols[mode] = name

        columns.append(name)

    # 중복 빈 컬럼/중복 이름 처리
    counts = {}
    deduped = []
    for name in columns:
        counts[name] = counts.get(name, 0) + 1
        if name == "":
            deduped.append(f"__EMPTY_{counts[name]}")
        elif columns.count(name) > 1 and name not in {"ELEC. CONSUMER", "OUTPUT(KW)", "INPUT(KW)", "Q'TY", "WORKING", "PT"}:
            deduped.append(f"{name}__{counts[name]}")
        else:
            deduped.append(name)

    # dedupe suffix 제거 후 매핑 재작성
    final_mode_cols = {}
    final_cl_cols = {}
    final_il_cols = {}
    for name in deduped:
        base = name.split("__")[0]
        for mode in modes:
            if base == f"{mode}_%" and mode not in final_mode_cols:
                final_mode_cols[mode] = name
            elif base == f"{mode}_C.L" and mode not in final_cl_cols:
                final_cl_cols[mode] = name
            elif base == f"{mode}_I.L" and mode not in final_il_cols:
                final_il_cols[mode] = name

    return deduped, modes, final_mode_cols, final_cl_cols, final_il_cols


# =========================================================
# ELA Parsing / Calculation Core
# =========================================================
def parse_ela_excel(file, il_df=2.0):
    """
    엑셀 ELA 파일을 읽어서
    1) 모드별 total load 결과(result)
    2) 상세 DataFrame(df)
    3) 추천 후보 placeholder(candidates)
    4) meta
    를 반환
    """
    result = {}
    candidates = []

    # 업로드 파일 객체 재사용 대비 포인터 초기화
    try:
        file.seek(0)
    except Exception:
        pass

    xls = pd.ExcelFile(file)
    target_sheet = _find_target_sheet(xls.sheet_names)
    if target_sheet is None:
        raise ValueError("'Anal' 또는 'Load Analysis' 계열 시트를 찾을 수 없습니다.")

    try:
        file.seek(0)
    except Exception:
        pass
    raw_df = pd.read_excel(file, sheet_name=target_sheet, header=None)

    header_row = _find_header_start(raw_df)
    columns, modes, mode_cols, cl_cols, il_cols = _build_columns(raw_df, header_row)

    data_start_row = header_row + 3
    df = raw_df.iloc[data_start_row:].reset_index(drop=True).copy()
    df.columns = columns

    consumer_col = "ELEC. CONSUMER" if "ELEC. CONSUMER" in df.columns else None
    input_col = "INPUT(KW)" if "INPUT(KW)" in df.columns else None
    output_col = "OUTPUT(KW)" if "OUTPUT(KW)" in df.columns else None
    qty_col = "Q'TY" if "Q'TY" in df.columns else None
    working_col = "WORKING" if "WORKING" in df.columns else None

    if not all([consumer_col, output_col, qty_col]):
        raise ValueError("필수 컬럼 부족 (ELEC. CONSUMER / OUTPUT(KW) / Q'TY 필요)")

    num_cols = [input_col, output_col, qty_col, working_col] + list(mode_cols.values()) + list(cl_cols.values()) + list(il_cols.values())
    num_cols = [c for c in num_cols if c and c in df.columns]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[df[consumer_col].notna()].copy()
    df[consumer_col] = df[consumer_col].astype(str).str.replace("\n", " ", regex=False).str.replace("\r", " ", regex=False).str.strip()
    df[consumer_col] = df[consumer_col].str.replace(r"\s+", " ", regex=True)

    # 집계행/구분행 제거
    # 예:
    # - SUB TOTAL, SUB TOTAL (1), GRAND TOTAL, TOTAL
    # - - MACH. PART, - ELECTRIC PART
    # - LOAD ANALYSIS TABLE, SHEET :
    exclude_contains_pattern = (
        r"SUB\s*TOTAL"
        r"|GRAND\s*TOTAL"
        r"|^TOTAL$"
        r"|LOAD\s*ANALYSIS"
        r"|SHEET\s*:"
        r"|-\s*.*PART"
        r"|PREFERENTIAL\s*TRIP\s*LOAD"
    )
    df = df[~df[consumer_col].str.contains(exclude_contains_pattern, case=False, na=False, regex=True)]
    df = df[df[consumer_col] != ""]

    # 완전히 비어 있는 잔여행 제거
    keep_cols = [c for c in [consumer_col, input_col, output_col, qty_col, working_col] if c in df.columns]
    df = df[df[keep_cols].notna().any(axis=1)].copy()

    # INPUT 보정: 입력값 없으면 OUTPUT / 효율 대신 기존 로직 유지(OUTPUT*0.8)
    df["INPUT_USED"] = df[input_col] if input_col else np.nan
    if output_col:
        df.loc[df["INPUT_USED"].isna(), "INPUT_USED"] = df[output_col] * 0.8

    # Q'TY/WORKING 기본값
    df[qty_col] = pd.to_numeric(df[qty_col], errors="coerce").fillna(1.0)
    if working_col:
        df[working_col] = pd.to_numeric(df[working_col], errors="coerce").fillna(df[qty_col]).fillna(1.0)
    else:
        df["WORKING"] = df[qty_col].fillna(1.0)
        working_col = "WORKING"

    df["LOAD_CATEGORY"] = df[consumer_col].apply(classify_load_category)

    for mode in modes:
        percent_col = mode_cols.get(mode)
        cl_col = cl_cols.get(mode)
        il_col = il_cols.get(mode)

        df[f"{mode}_CL"] = 0.0
        df[f"{mode}_IL"] = 0.0

        if percent_col and percent_col in df.columns:
            percent_series = pd.to_numeric(df[percent_col], errors="coerce")
        else:
            percent_series = pd.Series(np.nan, index=df.index)

        cl_series = pd.to_numeric(df[cl_col], errors="coerce") if cl_col and cl_col in df.columns else pd.Series(np.nan, index=df.index)
        il_series = pd.to_numeric(df[il_col], errors="coerce") if il_col and il_col in df.columns else pd.Series(np.nan, index=df.index)

        # 엑셀 직접입력 우선
        df[f"{mode}_CL"] = cl_series.fillna(0.0)
        df[f"{mode}_IL"] = il_series.fillna(0.0)

        # 둘 다 비어있고 %만 있으면 계산값을 CL로 반영
        calc_mask = percent_series.notna() & cl_series.isna() & il_series.isna()
        calc_val = (
            df["INPUT_USED"].fillna(0.0)
            * df[working_col].fillna(1.0)
            * (percent_series.fillna(0.0) / 100.0)
        )
        df.loc[calc_mask, f"{mode}_CL"] = calc_val[calc_mask]

        df[f"{mode}_IL_APPLIED"] = df[f"{mode}_IL"] / float(il_df)
        df[f"{mode}_TOTAL"] = df[f"{mode}_CL"] + df[f"{mode}_IL_APPLIED"]
        result[mode] = float(df[f"{mode}_TOTAL"].fillna(0).sum())

    mode_summary_df = build_mode_summary(df, modes, il_df)
    adapter_handoff_df = build_adapter_handoff_table(df, modes, il_df)

    meta = {
        "target_sheet": target_sheet,
        "header_row": header_row,
        "consumer_col": consumer_col,
        "input_col": input_col,
        "output_col": output_col,
        "qty_col": qty_col,
        "working_col": working_col,
        "modes": modes,
        "mode_cols": mode_cols,
        "cl_cols": cl_cols,
        "il_cols": il_cols,
        "il_df": il_df,
    }

    return result, df, candidates, meta, mode_summary_df, adapter_handoff_df


# =========================================================
# Page 1: Load Calculator
# =========================================================
def run_load_calculator():
    st.title("⚡ Diesel ELA Load Calculator")

    if "uploaded_file" not in st.session_state:
        st.session_state.uploaded_file = None

    uploaded_file = st.file_uploader("엑셀 파일 업로드", type=["xlsx", "xls"])

    if uploaded_file is not None:
        if st.session_state.uploaded_file != uploaded_file:
            st.session_state.calculated_result = {}
            st.session_state.main_df = pd.DataFrame()
            st.session_state.ela_meta = {}
            st.session_state.mode_summary_df = pd.DataFrame()
            st.session_state.adapter_handoff_df = pd.DataFrame()

        st.session_state.uploaded_file = uploaded_file

    file_to_use = st.session_state.uploaded_file

    il_df = st.number_input(
        "I.L Diversity Factor",
        min_value=1.0,
        max_value=5.0,
        value=2.0,
        step=0.5,
    )

    result = st.session_state.get("calculated_result", {})
    df = st.session_state.get("main_df", pd.DataFrame())
    meta = st.session_state.get("ela_meta", {})
    mode_summary_df = st.session_state.get("mode_summary_df", pd.DataFrame())
    adapter_handoff_df = st.session_state.get("adapter_handoff_df", pd.DataFrame())
    consumer_col = meta.get("consumer_col")
    adapter_handoff_df = st.session_state.get("adapter_handoff_df", pd.DataFrame())

    if file_to_use:
        try:
            result, df, candidates, meta, mode_summary_df, adapter_handoff_df = parse_ela_excel(file_to_use, il_df=il_df)

            st.session_state["main_df"] = df
            st.session_state["calculated_result"] = result
            st.session_state["ess_candidates"] = candidates
            st.session_state["ela_meta"] = meta
            st.session_state["mode_summary_df"] = mode_summary_df
            st.session_state["adapter_handoff_df"] = adapter_handoff_df

            consumer_col = meta.get("consumer_col")

        except Exception as e:
            st.error(f"❌ ELA 처리 오류: {e}")
            st.stop()

    if result:
        st.subheader("⚡ Mode별 Total Load (kW)")
        st.dataframe(mode_summary_df, use_container_width=True)
        st.caption("※ Total Load = Continuous Load + (Intermittent Load Raw / Div. Factor)")

        if not df.empty and consumer_col:
            st.subheader("🚤 Propulsion Loads")
            propulsion_df = df[df["LOAD_CATEGORY"] == "propulsion"].copy()
            prop_cols = [consumer_col]
            if meta.get("output_col") in propulsion_df.columns:
                prop_cols.append(meta["output_col"])
            st.dataframe(
                propulsion_df[prop_cols].rename(columns={meta.get("output_col"): "OUTPUT(KW)"}),
                use_container_width=True,
            )

            st.subheader("🛠️ Deck Machinery Loads")
            deck_df = df[df["LOAD_CATEGORY"] == "deck_machinery"].copy()
            deck_cols = [consumer_col]
            if meta.get("output_col") in deck_df.columns:
                deck_cols.append(meta["output_col"])
            st.dataframe(
                deck_df[deck_cols].rename(columns={meta.get("output_col"): "OUTPUT(KW)"}),
                use_container_width=True,
            )

            st.subheader("📋 상세 Load Table (수정 가능)")

            display_df = pd.DataFrame()
            display_df[consumer_col] = df[consumer_col]
            display_df["LOAD_CATEGORY"] = df["LOAD_CATEGORY"]

            if meta.get("output_col") in df.columns:
                display_df["OUTPUT"] = df[meta["output_col"]]
            if meta.get("input_col") in df.columns:
                display_df["INPUT"] = df[meta["input_col"]]
            if meta.get("qty_col") in df.columns:
                display_df["Q'TY"] = df[meta["qty_col"]]
            if meta.get("working_col") in df.columns:
                display_df["WORKING"] = df[meta["working_col"]]

            for mode in meta.get("modes", []):
                percent_col = meta.get("mode_cols", {}).get(mode)

                if percent_col in df.columns:
                    display_df[f"{mode}_L.F"] = df[percent_col]

                calc_cl_col = f"{mode}_CL"
                calc_il_col = f"{mode}_IL"
                calc_il_applied_col = f"{mode}_IL_APPLIED"

                if calc_cl_col in df.columns:
                    display_df[f"{mode}_C.L"] = df[calc_cl_col]
                if calc_il_col in df.columns:
                    display_df[f"{mode}_I.L_RAW"] = df[calc_il_col]
                if calc_il_applied_col in df.columns:
                    display_df[f"{mode}_I.L_APPLIED"] = df[calc_il_applied_col]

            for col in ["Q'TY", "WORKING"]:
                if col in display_df.columns:
                    display_df[col] = pd.to_numeric(display_df[col], errors="coerce").fillna(0).astype(int)

            for col in display_df.columns:
                if col not in ["Q'TY", "WORKING", consumer_col, "LOAD_CATEGORY"]:
                    if pd.api.types.is_numeric_dtype(display_df[col]):
                        display_df[col] = display_df[col].round(2)

            edited_df = st.data_editor(display_df, use_container_width=True)
            st.caption("※ 현재 단계에서는 미리보기용이며, 이후 app.py와 연결 시 adapter를 통해 전달 예정")


# =========================================================
# Page 2: App Integration Preview
# =========================================================
def run_app_bridge():
    st.title("🔗 App.py Integration Preview")
    st.caption("Dynamic Profile Studio 대신 app.py 연동을 위한 중간 확인 페이지")

    result = st.session_state.get("calculated_result", {})
    df = st.session_state.get("main_df", pd.DataFrame())
    meta = st.session_state.get("ela_meta", {})
    mode_summary_df = st.session_state.get("mode_summary_df", pd.DataFrame())
    adapter_handoff_df = st.session_state.get("adapter_handoff_df", pd.DataFrame())

    if not result:
        st.info("먼저 Load Calculator (Excel)에서 ELA를 읽어주세요.")
        return

    st.subheader("0) 1단계 작업용 체크리스트")
    st.dataframe(build_step1_checklist(), use_container_width=True)

    st.subheader("1) 전달 예정 요약값")
    st.dataframe(mode_summary_df, use_container_width=True)

    st.subheader("2) 전달 예정 메타정보")
    meta_view = pd.DataFrame([(k, str(v)) for k, v in meta.items()], columns=["Key", "Value"])
    st.dataframe(meta_view, use_container_width=True)

    st.subheader("3) 상세 Data Preview")
    if not df.empty:
        preview_cols = [c for c in df.columns if any(key in str(c).upper() for key in ["ELEC. CONSUMER", "INPUT", "OUTPUT", "LOAD_CATEGORY", "_CL", "_IL", "_TOTAL"])]
        st.dataframe(df[preview_cols].head(200), use_container_width=True)
    else:
        st.warning("상세 데이터가 비어 있습니다.")

    st.subheader("4) adapters.py 전달 예정 데이터")
    st.dataframe(adapter_handoff_df, use_container_width=True)

    st.subheader("5) app.py 연결 방향")
    st.markdown(
        """
        - 이 페이지는 Dynamic Profile Studio를 제거하고,
          **ELA 결과를 app.py로 넘기기 전 확인하는 용도**로 변경한 상태입니다.
        - 이후 통합 시에는 아래 흐름으로 연결하면 됩니다.
          **ELA Excel → parse_ela_excel() → result / df / meta / mode_summary_df → adapter → app.py input_data**
        - 현재는 코드를 합치기 전 단계이므로, 여기서는 **미리보기와 handoff 확인만 수행**합니다.
        """
    )


def main() -> None:
    st.set_page_config(page_title="Marine Electrical Studio", layout="wide")

    if "page" not in st.session_state:
        st.session_state.page = "Calculator"

    with st.sidebar:
        st.title("🚢 Main Menu")

        if st.button("📊 Load Calculator (Excel)", use_container_width=True):
            st.session_state.page = "Calculator"

        if st.button("🔗 App.py Integration", use_container_width=True):
            st.session_state.page = "Bridge"

    if st.session_state.page == "Calculator":
        run_load_calculator()
    elif st.session_state.page == "Bridge":
        run_app_bridge()


if __name__ == "__main__":
    main()
