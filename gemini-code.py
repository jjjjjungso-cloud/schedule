import streamlit as st
import pandas as pd
import re
from datetime import datetime

# --- 데이터 파싱 함수 ---
def parse_actual_work(cell_value):
    """
    P-D4/116 같은 데이터를 (근무: D, 병동: 116)으로 분리합니다.
    D4, D6 등 숫자가 붙은 단축 근무도 D로 통일합니다.
    """
    val = str(cell_value).strip()
    
    # 1. 휴무 및 제외 키워드 처리 (건, 필, ET, /, 빈값 등)
    off_keywords = ['건', '필', 'ET', '/', 'nan', 'None', '']
    if not val.startswith('P-') and any(k in val for k in off_keywords):
        return "OFF", None

    # 2. P- 데이터 해석 (정규식 사용)
    # 패턴: P- 뒤의 첫 알파벳([a-zA-Z]) 추출, / 뒤의 숫자(\d+) 추출
    match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
    if match:
        shift = match.group(1).upper() # D4 -> D
        ward = match.group(2)          # 092 -> 092
        return shift, ward
    
    return "OFF", None

# --- UI 설정 ---
st.set_page_config(page_title="프라임 데이터 통합 분석", layout="wide")
st.title("🏥 프라임 데이터 정제 및 일자별 추출")

# 사이드바 설정
st.sidebar.header("📅 분석 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("대상 월", [f"{i}월" for i in range(1, 13)], index=3)

col_plan, col_actual = st.columns(2)

# [1. 배정표 영역]
with col_plan:
    st.header("1️⃣ 배정표(Plan) 업로드")
    file_p = st.file_uploader("배정표(.xlsx) 선택", type="xlsx", key="plan_up")
    if file_p:
        xl_p = pd.ExcelFile(file_p)
        sheet_p = st.selectbox("계획 시트 선택", xl_p.sheet_names)
        df_p_raw = pd.read_excel(file_p, sheet_name=sheet_p)
        st.success(f"✅ '{sheet_p}' 계획 데이터 로드 완료")
        st.dataframe(df_p_raw.head(), use_container_width=True)

# [2. 근무표 영역]
with col_actual:
    st.header("2️⃣ 실제 근무표(Actual) 업로드")
    file_a = st.file_uploader("실제 근무표(.xlsx) 선택", type="xlsx", key="actual_up")
    
    if file_a:
        xl_a = pd.ExcelFile(file_a)
        sheet_a = st.selectbox("근무 시트 선택", xl_a.sheet_names)
        # 실제 데이터가 보통 3~4행부터 시작하므로 상황에 따라 header 조정 필요
        df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
        
        st.success(f"✅ '{sheet_a}' 실제 근무 데이터 로드 완료")
        
        # --- 데이터 추출 로직 가동 ---
        actual_data_list = []
        
        # 3월과 4-5월의 구조 차이를 고려한 동적 추출
        # C열(성함): index 2 / H열(1일): index 7 가정
        for index, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip()
            if name == 'nan' or len(name) < 2: continue # 이름이 없는 행 스킵
            
            # H열 이후 모든 날짜 열을 순회
            for col_idx in range(7, len(df_a_raw.columns)):
                col_name = str(df_a_raw.columns[col_idx])
                # 열 제목에서 숫자(일자)만 추출
                day_match = re.search(r'\d+', col_name)
                
                if day_match:
                    day = day_match.group()
                    cell_val = row.iloc[col_idx]
                    shift, ward = parse_actual_work(cell_val)
                    
                    if shift != "OFF":
                        actual_data_list.append({
                            "성함": name,
                            "날짜": f"{selected_year}-{selected_month}-{day}일",
                            "근무": shift,
                            "지원병동": ward
                        })

        df_actual_final = pd.DataFrame(actual_data_list)
        
        with st.expander("🔍 일자별 근무 추출 결과 확인"):
            if not df_actual_final.empty:
                st.dataframe(df_actual_final, use_container_width=True)
                st.info(f"총 {len(df_actual_final)}건의 실제 근무 기록이 추출되었습니다.")
            else:
                st.warning("추출된 근무 데이터가 없습니다. 열 위치를 확인해주세요.")

# --- 최종 결과 버튼 ---
st.markdown("---")
if not df_actual_final.empty and file_p:
    if st.button("🚀 정합성 분석 시작 (계획 vs 실제)"):
        st.balloons()
        # 이후 여기에 df_p_raw와 df_actual_final을 병합(merge)하는 코드를 추가하면 됩니다.
        st.write("두 데이터를 비교할 준비가 되었습니다!")
