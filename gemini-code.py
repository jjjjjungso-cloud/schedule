import streamlit as st
import pandas as pd
import re
from datetime import datetime

# --- [1. 데이터 파싱 엔진] ---
def parse_actual_work(cell_value):
    """
    P-D4/116 같은 데이터를 (근무: D, 병동: 116)으로 분리.
    D4, D6 등 숫자가 붙은 단축 근무도 D로 통일.
    휴무 키워드(건, 필, ET, /)는 OFF 반환.
    """
    val = str(cell_value).strip()
    
    # 휴무 및 제외 키워드 처리
    off_keywords = ['건', '필', 'ET', '/', 'nan', 'None', '']
    if not val.startswith('P-') and any(k in val for k in off_keywords):
        return "OFF", None

    # P- 데이터 해석 (D4, D6 등 대응)
    match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
    if match:
        shift = match.group(1).upper() # D4 -> D
        ward = match.group(2)          # 병동 번호
        return shift, ward
    
    return "OFF", None

# --- [2. UI 설정] ---
st.set_page_config(page_title="프라임 근무 데이터 통합 분석", layout="wide")
st.title("🏥 프라임 간호사 데이터 정제 및 정합성 검증")

st.sidebar.header("📅 기본 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
# 사이드바 월 설정은 참고용이며, 실제 데이터 추출은 시트 이름을 우선합니다.
selected_month_sidebar = st.sidebar.selectbox("기준 월", [f"{i}월" for i in range(1, 13)], index=3)

st.markdown("---")
col_plan, col_actual = st.columns(2)

# --- [3. 배정표(Plan) 영역] ---
with col_plan:
    st.header("1️⃣ 배정표(Plan) 업로드")
    file_p = st.file_uploader("주간 배정표(.xlsx) 선택", type="xlsx", key="plan_up")
    
    df_plan_std = pd.DataFrame()
    if file_p:
        xl_p = pd.ExcelFile(file_p)
        sheet_p = st.selectbox("분석할 시트 선택 (계획)", xl_p.sheet_names)
        df_p_raw = pd.read_excel(file_p, sheet_name=sheet_p)
        
        # E, H, I, L, O열 추출 (성함 및 병동 정보)
        try:
            df_plan_std = df_p_raw.iloc[:, [4, 7, 8, 11, 14]].copy()
            df_plan_std.columns = ['성함', '배정1', '배정2', '배정3', '배정4']
            df_plan_std = df_plan_std.dropna(subset=['성함'])
            st.success("✅ 배정표 정제 완료")
            st.dataframe(df_plan_std.head(), use_container_width=True)
        except:
            st.error("배정표 열 구조가 일치하지 않습니다.")

# --- [4. 실제 근무표(Actual) 영역] ---
with col_actual:
    st.header("2️⃣ 실제 근무표(Actual) 업로드")
    file_a = st.file_uploader("월간 근무표(.xlsx) 선택", type="xlsx", key="actual_up")
    
    df_actual_final = pd.DataFrame()
    if file_a:
        xl_a = pd.ExcelFile(file_a)
        sheet_a = st.selectbox("분석할 시트 선택 (실제)", xl_a.sheet_names)
        df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
        
        # [핵심] 시트 이름에서 실제 월(Month) 추출 (사이드바 설정 오류 방지)
        extracted_month = re.sub(r'[^0-9]', '', sheet_a)
        if not extracted_month: # 시트 이름에 숫자가 없으면 사이드바 값 사용
            extracted_month = re.sub(r'[^0-9]', '', selected_month_sidebar)

        actual_data_list = []

        # C열(이름): index 2 / H열(1일): index 7
        for index, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip()
            if name == 'nan' or len(name) < 2: continue
            
            # 날짜 열 순회
            for col_idx in range(7, len(df_a_raw.columns)):
                col_name = str(df_a_raw.columns[col_idx])
                day_match = re.search(r'\d+', col_name)
                
                if day_match:
                    day = day_match.group()
                    cell_val = row.iloc[col_idx]
                    shift, ward = parse_actual_work(cell_val)
                    
                    if shift != "OFF":
                        # 정확한 월과 일자를 조합
                        date_full = f"{selected_year}-{extracted_month.zfill(2)}-{day.zfill(2)}"
                        actual_data_list.append({
                            "성함": name,
                            "날짜": date_full,
                            "근무": shift,
                            "지원병동": ward
                        })

        df_actual_final = pd.DataFrame(actual_data_list)
        
        if not df_actual_final.empty:
            st.success(f"✅ {extracted_month}월 근무 데이터 추출 완료")
            st.dataframe(df_actual_final.head(), use_container_width=True)
        else:
            st.warning("추출된 데이터가 없습니다.")

# --- [5. 최종 정합성 분석] ---
st.markdown("---")
if not df_plan_std.empty and not df_actual_final.empty:
    if st.button("🚀 데이터 정합성 분석 시작"):
        # 성함을 기준으로 두 데이터 병합
        # (실제 환경에서는 날짜까지 매칭하는 로직이 추가될 수 있음)
        df_merge = pd.merge(df_actual_final, df_plan_std, on="성함", how="left")
        
        st.subheader("🔍 분석 결과 (계획 대비 실제)")
        st.dataframe(df_merge, use_container_width=True)
        st.balloons()
else:
    st.info("💡 배정표와 근무표를 모두 업로드하면 분석을 시작할 수 있습니다.")
