import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [1. 데이터 파싱 공통 함수] ---
def parse_actual_work(cell_value):
    """P-D4/116 형식을 (근무: D, 병동: 116)으로 분리"""
    val = str(cell_value).strip()
    off_keywords = ['건', '필', 'ET', '/', 'nan', 'None', '']
    # P-로 시작하지 않으면서 휴무 키워드가 있거나 빈 값인 경우 OFF
    if not val.startswith('P-') and (any(k in val for k in off_keywords) or val == ''):
        return "OFF", None
    
    # D4, D6 등 숫자가 붙어도 첫 알파벳만 가져오고, / 뒤의 병동 숫자 추출
    match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
    if match:
        return match.group(1).upper(), match.group(2)
    return "OFF", None

def expand_plan_period(df_p, year=2026):
    """배정표의 기간(3/3~3/13)을 개별 날짜 행으로 확장"""
    expanded_rows = []
    for _, row in df_p.iterrows():
        try:
            # 컬럼명이 '시작일', '종료일'일 경우를 가정 (사용자 엑셀에 맞춰 수정 가능)
            start_p = str(row['시작일'])
            end_p = str(row['종료일'])
            
            # 날짜 파싱 (월/일 형태 추출)
            sm, sd = map(int, re.findall(r'\d+', start_p))
            em, ed = map(int, re.findall(r'\d+', end_p))
            
            curr_date = datetime(year, sm, sd)
            end_date = datetime(year, em, ed)
            
            while curr_date <= end_date:
                expanded_rows.append({
                    "날짜": curr_date.strftime('%Y-%m-%d'),
                    "근무": str(row['근무조']).strip(),
                    "병동": str(row['배정병동']).strip(),
                    "성함": str(row['간호사 성함']).strip()
                })
                curr_date += timedelta(days=1)
        except:
            continue
    return pd.DataFrame(expanded_rows)

# --- [2. UI 설정] ---
st.set_page_config(page_title="프라임 통합 분석 시스템", layout="wide")
st.title("🏥 프라임 데이터 일자별 통합 및 정합성 검증")

st.sidebar.header("📅 분석 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month_sidebar = st.sidebar.selectbox("대상 월", [f"{i}월" for i in range(1, 13)], index=3)

col_plan, col_actual = st.columns(2)

# --- [3. 1단계: 배정표(Plan) 확장] ---
df_p_final = pd.DataFrame()
with col_plan:
    st.header("1️⃣ 배정표(계획) 일자별 확장")
    file_p = st.file_uploader("주간 배정표(.xlsx) 업로드", type="xlsx", key="p")
    if file_p:
        df_p_raw = pd.read_excel(file_p)
        df_p_final = expand_plan_period(df_p_raw, selected_year)
        if not df_p_final.empty:
            st.success("✅ 계획 데이터 확장 완료")
            st.dataframe(df_p_final[["날짜", "근무", "병동", "성함"]], use_container_width=True)

# --- [4. 2단계: 실제 근무표(Actual) 추출 - 자동 열 탐색 적용] ---
df_a_final = pd.DataFrame()
with col_actual:
    st.header("2️⃣ 실제 근무표(실제) 형식 통일")
    file_a = st.file_uploader("월간 근무표(.xlsx) 업로드", type="xlsx", key="a")
    if file_a:
        xl_a = pd.ExcelFile(file_a)
        sheet_a = st.selectbox("분석할 시트 선택", xl_a.sheet_names)
        df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
        
        # [수정된 로직] 1일부터 시작되는 열 인덱스 자동 찾기
        start_col_idx = None
        for i, col in enumerate(df_a_raw.columns):
            if '1' in str(col): # '1일' 혹은 '1'이 포함된 제목 찾기
                start_col_idx = i
                break
        
        if start_col_idx is None: start_col_idx = 7 # 못 찾을 경우 기본값 H열
        
        # 시트 이름에서 월 정보 추출
        extracted_month = re.sub(r'[^0-9]', '', sheet_a)
        if not extracted_month: extracted_month = re.sub(r'[^0-9]', '', selected_month_sidebar)

        actual_rows = []
        for index, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip() # C열 성함
            if name == 'nan' or len(name) < 2: continue
            
            for col_idx in range(start_col_idx, len(df_a_raw.columns)):
                col_name = str(df_a_raw.columns[col_idx])
                day_match = re.search(r'\d+', col_name)
                
                if day_match:
                    day = day_match.group()
                    cell_val = row.iloc[col_idx]
                    shift, ward = parse_actual_work(cell_val)
                    
                    if shift != "OFF":
                        date_str = f"{selected_year}-{extracted_month.zfill(2)}-{day.zfill(2)}"
                        actual_rows.append({
                            "날짜": date_str,
                            "근무": shift,
                            "병동": ward,
                            "성함": name
                        })
        
        df_a_final = pd.DataFrame(actual_rows)
        if not df_a_final.empty:
            st.success(f"✅ {extracted_month}월 실제 근무 데이터 추출 완료")
            st.dataframe(df_a_final[["날짜", "근무", "병동", "성함"]], use_container_width=True)

# --- [5. 3단계: 통합 비교 분석] ---
st.markdown("---")
if not df_p_final.empty and not df_a_final.empty:
    if st.button("🚀 계획 vs 실제 정합성 분석 시작"):
        # 날짜와 성함을 기준으로 두 데이터 병합
        df_merge = pd.merge(
            df_a_final, 
            df_p_final, 
            on=["날짜", "성함"], 
            how="outer", 
            suffixes=("_실제", "_계획")
        )
        
        # 불일치 여부 체크 함수
        def check_diff(row):
            if pd.isna(row['병동_계획']): return "계획 외 지원"
            if pd.isna(row['병동_실제']): return "계획 미이행"
            if row['병동_실제'] != row['병동_계획']: return "병동 불일치"
            return "정상"

        df_merge['분석결과'] = df_merge.apply(check_diff, axis=1)
        st.subheader("🔍 최종 비교 분석 결과")
        st.dataframe(df_merge, use_container_width=True)
        
        # 사이드바에 통계 요약
        st.sidebar.markdown("### 📊 분석 요약")
        st.sidebar.write(df_merge['분석결과'].value_counts())
