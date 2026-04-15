import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Marine Electrical Studio", layout="wide")


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
    """
    1단계 작업용 체크리스트
    - ela_read.py의 출력 계약을 먼저 고정하기 위한 확인표
    """
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
    """
    adapters.py에 넘길 표준 요약 테이블 생성
    """
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

    xls = pd.ExcelFile(file)
    target_sheet = None

    for sheet in xls.sheet_names:
        if "anal" in sheet.lower():
            target_sheet = sheet
            break

    if target_sheet is None:
        raise ValueError("'anal' 포함된 시트를 찾을 수 없음")

    # 3줄 헤더
    df = pd.read_excel(file, sheet_name=target_sheet, header=[1, 2, 3])

    # -----------------------------------------
    # 헤더 재구성 규칙
    # 1열(인덱스 0) : 버림
    # 2~6열(인덱스 1~5), 22열(인덱스 21) : 첫 번째 헤더 사용(표준명 정리)
    # 7~21열(인덱스 6~20) : 두 번째 헤더 첫 단어 + 세 번째 헤더 첫 3글자
    # mode는 7~21열의 두 번째 헤더에서 동적으로 추출
    # -----------------------------------------
    def clean_text(x):
        if pd.isna(x):
            return ""
        x = str(x).replace("\n", " ").replace("\r", " ").strip().upper()
        if x.startswith("UNNAMED:") or x == "NAN":
            return ""
        return x

    def first_word(x):
        x = clean_text(x)
        if not x:
            return ""
        return x.split(" ")[0]

    def first_three(x):
        x = clean_text(x)
        return x[:3]

    new_columns = []
    detected_modes = []

    for idx, col in enumerate(df.columns.values):
        h1, h2, h3 = col

        c1 = clean_text(h1)
        c2 = clean_text(h2)
        c3 = clean_text(h3)

        # 1열 버림
        if idx == 0:
            new_columns.append("")
            continue

        # 2~6열 + 22열 : 첫 번째 헤더 사용 + 표준명 정리
        if 1 <= idx <= 5 or idx == 21:
            if "ELECTRIC" in c1 and "CONSUMER" in c1:
                new_columns.append("ELEC. CONSUMER")
            elif "OUTPUT" in c1:
                new_columns.append("OUTPUT(KW)")
            elif "INPUT" in c1:
                new_columns.append("INPUT(KW)")
            elif "Q" in c1:
                new_columns.append("Q'TY")
            elif "WORK" in c1:
                new_columns.append("WORKING")
            elif "PT" in c1:
                new_columns.append("PT")
            else:
                new_columns.append(c1)
            continue

        # 7~21열 : mode + sub 헤더
        if 6 <= idx <= 20:
            mode = first_word(h2)
            sub3 = first_three(h3)

            if sub3.startswith("%"):
                sub = "%"
            elif sub3 == "C.L":
                sub = "C.L"
            elif sub3 == "I.L":
                sub = "I.L"
            else:
                sub = ""

            if mode:
                detected_modes.append(mode)

            if mode and sub:
                new_columns.append(f"{mode}_{sub}")
            else:
                new_columns.append("")
            continue

        # 나머지는 첫 번째 헤더 사용
        new_columns.append(c1)

    df.columns = new_columns

    # mode 중복 제거, 순서 유지
    modes = list(dict.fromkeys([m for m in detected_modes if m]))

    # 중복 컬럼 처리
    cols = pd.Series(df.columns)
    for dup_name in cols[cols.duplicated()].unique():
        dup_idx = cols[cols == dup_name].index.tolist()
        for n, idx in enumerate(dup_idx, start=1):
            if dup_name in ["", "PT"]:
                cols.iloc[idx] = f"{dup_name}__{n}"
            else:
                cols.iloc[idx] = dup_name
    df.columns = cols.tolist()

    def find_col(*keywords):
        for col in df.columns:
            clean_col = col.upper()
            clean_keywords = [k.upper() for k in keywords]
            if all(k in clean_col for k in clean_keywords):
                return col
        return None

    consumer_col = "ELEC. CONSUMER" if "ELEC. CONSUMER" in df.columns else None
    input_col = find_col("INPUT")
    output_col = find_col("OUTPUT")
    qty_col = find_col("Q")
    working_col = find_col("WORK")

    if not all([consumer_col, output_col, qty_col]):
        raise ValueError("필수 컬럼 부족 (OUTPUT / QTY 필요)")

    mode_cols = {}
    cl_cols = {}
    il_cols = {}

    for mode in modes:
        mode_cols[mode] = find_col(mode, "%")
        cl_cols[mode] = find_col(mode, "C.L")
        il_cols[mode] = find_col(mode, "I.L")

    # 숫자 컬럼 변환
    num_cols = [input_col, output_col, qty_col, working_col] + list(mode_cols.values()) + list(cl_cols.values()) + list(il_cols.values())
    num_cols = [c for c in num_cols if c]

    for col in num_cols:
        if col in df.columns:
            if isinstance(df[col], pd.DataFrame):
                # 같은 이름 컬럼이 여러 개면 첫 번째만 사용
                df[col] = pd.to_numeric(df[col].iloc[:, 0], errors="coerce")
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    # 유효 행 정리
    df = df[df[consumer_col].notna()].copy()
    df[consumer_col] = df[consumer_col].astype(str).str.strip()

    exclude_keywords = "ELECTRIC CONSUMER|TOTAL|GRAND|SUB|OUTPUT|INPUT|QTY|SERVICE|nan|None"
    df = df[~df[consumer_col].str.contains(exclude_keywords, na=False, case=False)]
    df = df[df[consumer_col] != ""]

    # INPUT 보정
    df["INPUT_USED"] = df[input_col] if input_col else np.nan
    if output_col:
        df.loc[df["INPUT_USED"].isna(), "INPUT_USED"] = df[output_col] * 0.8

    # 부하 분류
    df["LOAD_CATEGORY"] = df[consumer_col].apply(classify_load_category)

    # mode별 계산
    for mode in modes:
        percent_col = mode_cols.get(mode)
        cl_col = cl_cols.get(mode)
        il_col = il_cols.get(mode)

        df[f"{mode}_CL"] = 0.0
        df[f"{mode}_IL"] = 0.0

        for row_idx in df.index:
            percent = df.at[row_idx, percent_col] if percent_col else np.nan
            if pd.isna(percent):
                continue

            cl_val = df.at[row_idx, cl_col] if cl_col else np.nan
            il_val = df.at[row_idx, il_col] if il_col else np.nan

            # 둘 다 직접 입력되어 있으면 일단 둘 다 반영
            if pd.notna(cl_val):
                df.at[row_idx, f"{mode}_CL"] = cl_val

            if pd.notna(il_val):
                df.at[row_idx, f"{mode}_IL"] = il_val

            # 둘 다 없을 때만 계산값 사용
            if pd.isna(cl_val) and pd.isna(il_val):
                working_val = df.at[row_idx, working_col] if working_col else 1.0
                input_used = df.at[row_idx, "INPUT_USED"]

                if pd.isna(working_val):
                    working_val = 1.0
                if pd.isna(input_used):
                    input_used = 0.0

                val = input_used * working_val * (percent / 100.0)
                df.at[row_idx, f"{mode}_CL"] = val

        df[f"{mode}_IL_APPLIED"] = df[f"{mode}_IL"] / il_df
        df[f"{mode}_TOTAL"] = df[f"{mode}_CL"] + df[f"{mode}_IL_APPLIED"]
        result[mode] = df[f"{mode}_TOTAL"].sum()

    mode_summary_df = build_mode_summary(df, modes, il_df)
    adapter_handoff_df = build_adapter_handoff_table(df, modes, il_df)

    meta = {
        "target_sheet": target_sheet,
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

                # %는 원본 열 사용, 헤더는 [MODE]_L.F
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

            # Q'TY, WORKING 정수 표시
            for col in ["Q'TY", "WORKING"]:
                if col in display_df.columns:
                    display_df[col] = pd.to_numeric(display_df[col], errors="coerce").fillna(0).astype(int)

            # 나머지 숫자: 소수 둘째자리까지
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


# =========================================================
# Main Menu
# =========================================================
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
