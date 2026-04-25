import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 페이지 설정 ---
st.set_page_config(page_title="프라임 데이터 통합 검증", layout="wide")

# --- 정제 함수 (모든 데이터를 한 번에 가져오기) ---

def clean_actual_all_data(uploaded_file, year):
    """모든 시트를 순회하며 P- 코드를 전부 추출"""
    xl = pd.ExcelFile(uploaded_file)
    all_actual_list = []
    
    for sheet_name in xl.sheet_names:
        # 시트 이름에서 숫자(월) 추출 (예: '3월 근무표' -> 3)
        month_match = re.findall(r'\d+', sheet_name)
        if not month_match: continue
        month_int = int(month_match[0])
        
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '', 'None']: continue
            
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        shift = 'D' if ('D4' in code or 'D' in code) else 'E'
                        try:
                            date_val = datetime(year, month_int, int(d_match[0]))
                            all_actual_list.append({
                                '날짜': date_val, # 필터링을 위해 datetime 객체로 유지
                                '성함': name,
                                '근무조': shift,
                                '병동': str(int(ward_match.group(1))),
                                '원본월': f"{month_int}월" 
                            })
                        except: continue
                            
    return pd.DataFrame(all_actual_list)

def expand_plan_all_data(df):
    """배정표 전체 데이터를 날짜별로 펼치기"""
    expanded_list = []
    for _, row in df.iterrows():
        try:
            start_date = pd.to_datetime(row['시작일'])
            end_date = pd.to_datetime(row['종료일'])
            curr = start_date
            while curr <= end_date:
                expanded_list.append({
                    '날짜': curr,
                    '성함': str(row['간호사 성함']).strip(),
                    '근무조': row['근무조'],
                    '병동': str(row['배정병동'])
                })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

# --- 메인 UI ---
st.title("🏥 프라임 데이터 통합 분석 시스템")

# 1. 파일 업로드 단계
st.header("1️⃣ 파일 업로드")
col1, col2 = st.columns(2)
with col1:
    file_p = st.file_uploader("계획표(Plan) 업로드", type="xlsx")
with col2:
    file_a = st.file_uploader("실제근무표(Actual) 업로드", type="xlsx")

if file_p and file_a:
    # 데이터 처리 (세션 스테이트를 사용하여 한 번만 계산)
    if 'df_plan' not in st.session_state:
        xl_p = pd.ExcelFile(file_p)
        df_p_raw = pd.read_excel(file_p, sheet_name=xl_p.sheet_names[0])
        st.session_state.df_plan = expand_plan_all_data(df_p_raw)
        
    if 'df_actual' not in st.session_state:
        # 기준 연도는 사이드바에서 하나만 받음
        base_year = st.sidebar.number_input("데이터 기준 연도", value=2026)
        st.session_state.df_actual = clean_actual_all_data(file_a, base_year)

    st.divider()

    # 2. 필터 및 조회 단계
    st.header("2️⃣ 데이터 조회 및 필터")
    
    # 여기서 월을 선택!
    available_months = sorted(st.session_state.df_actual['날짜'].dt.month.unique())
    selected_month = st.select_slider("조회할 월을 선택하세요", options=available_months, value=min(available_months))

    # 데이터 필터링
    filtered_plan = st.session_state.df_plan[st.session_state.df_plan['날짜'].dt.month == selected_month].copy()
    filtered_actual = st.session_state.df_actual[st.session_state.df_actual['날짜'].dt.month == selected_month].copy()

    # 날짜 형식 예쁘게 출력용 변환
    filtered_plan['날짜'] = filtered_plan['날짜'].dt.strftime('%Y-%m-%d')
    filtered_actual['날짜'] = filtered_actual['날짜'].dt.strftime('%Y-%m-%d')

    col_res1, col_res2 = st.columns(2)
    with col_res1:
        st.subheader(f"📋 {selected_month}월 계획 데이터")
        st.dataframe(filtered_plan, use_container_width=True)
    
    with col_res2:
        st.subheader(f"📋 {selected_month}월 실제 근무(P-코드)")
        st.dataframe(filtered_actual, use_container_width=True)

    # 3. 다음 단계 제안
    if not filtered_plan.empty and not filtered_actual.empty:
        st.success(f"✅ {selected_month}월 데이터 정제가 완료되었습니다.")
        if st.button(f"{selected_month}월 데이터 차이점 분석하기"):
            st.write("분석 로직 가동 중...") # 여기에 머지(Merge) 로직 추가 예정
