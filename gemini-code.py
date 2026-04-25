import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 페이지 설정 ---
st.set_page_config(page_title="프라임 데이터 정제 및 검증", layout="wide")

# --- [유틸리티 함수] 실제 근무표 정제 (모든 시트 통합 버전) ---
def clean_actual_all_data(uploaded_file, year):
    xl = pd.ExcelFile(uploaded_file)
    all_actual_list = []
    
    for sheet_name in xl.sheet_names:
        # 시트 이름에서 월 추출 (예: '3월', '4월 근무표' -> 3, 4)
        m_match = re.findall(r'\d+', sheet_name)
        if not m_match: continue
        month_int = int(m_match[0])
        
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
                            # 필터링을 위해 datetime 객체로 저장
                            date_obj = datetime(year, month_int, int(d_match[0]))
                            all_actual_list.append({
                                '날짜': date_obj,
                                '성함': name,
                                '근무조': shift,
                                '병동': str(int(ward_match.group(1)))
                            })
                        except: continue
    return pd.DataFrame(all_actual_list)

# --- [유틸리티 함수] 배정표(계획) 펼치기 ---
def expand_plan_data(df):
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    if not all(col in df.columns for col in required):
        return pd.DataFrame()

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
st.title("🏥 프라임 데이터 입력 및 월별 검증")

# 사이드바 설정 (기준 연도)
st.sidebar.header("📅 분석 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)

tab1, tab2, tab3 = st.tabs(["📂 1단계: 파일 업로드", "🔍 2단계: 데이터 정제", "📅 3단계: 월별 상세 조회"])

# 전역 변수 대신 세션 스테이트 사용하여 데이터 유지
if 'final_plan' not in st.session_state: st.session_state.final_plan = None
if 'final_actual' not in st.session_state: st.session_state.final_actual = None

with tab1:
    col_p, col_a = st.columns(2)
    with col_p:
        st.header("1️⃣ 배정표(계획) 업로드")
        file_p = st.file_uploader("주간 배정표(.xlsx) 선택", type="xlsx", key="p_up")
    with col_a:
        st.header("2️⃣ 실제 근무표(Actual) 업로드")
        file_a = st.file_uploader("월간 근무표(.xlsx) 선택", type="xlsx", key="a_up")

with tab2:
    if file_p and file_a:
        if st.button("🚀 전체 데이터 정제 실행"):
            # 계획 데이터 정제
            xl_p = pd.ExcelFile(file_p)
            df_p_raw = pd.read_excel(file_p, sheet_name=xl_p.sheet_names[0])
            st.session_state.final_plan = expand_plan_data(df_p_raw)
            
            # 실제 데이터 정제 (모든 시트)
            st.session_state.final_actual = clean_actual_all_data(file_a, selected_year)
            
            st.success("✅ 모든 시트의 데이터 정제가 완료되었습니다! 3단계 탭에서 월별로 확인하세요.")
            
            col1, col2 = st.columns(2)
            col1.metric("계획 데이터 수", f"{len(st.session_state.final_plan)}건")
            col2.metric("실제(P코드) 데이터 수", f"{len(st.session_state.final_actual)}건")
    else:
        st.warning("파일을 먼저 업로드해주세요.")

with tab3:
    if st.session_state.final_plan is not None and st.session_state.final_actual is not None:
        # 데이터에서 월 목록 추출 (중복 제거 및 정렬)
        actual_months = sorted(st.session_state.final_actual['날짜'].dt.month.unique())
        
        if not actual_months:
            st.warning("분석할 수 있는 월 데이터가 없습니다.")
        else:
            # 월별로 탭 생성
            month_tabs = st.tabs([f"{m}월" for m in actual_months])
            
            for i, m in enumerate(actual_months):
                with month_tabs[i]:
                    st.subheader(f"📅 {selected_year}년 {m}월 데이터 현황")
                    
                    # 해당 월 데이터 필터링
                    m_plan = st.session_state.final_plan[st.session_state.final_plan['날짜'].dt.month == m].copy()
                    m_actual = st.session_state.final_actual[st.session_state.final_actual['날짜'].dt.month == m].copy()
                    
                    # 출력을 위해 날짜 형식 포맷팅
                    m_plan['날짜'] = m_plan['날짜'].dt.strftime('%Y-%m-%d')
                    m_actual['날짜'] = m_actual['날짜'].dt.strftime('%Y-%m-%d')
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.info(f"📋 {m}월 계획(Plan)")
                        st.dataframe(m_plan, use_container_width=True, height=400)
                    with c2:
                        st.success(f"📋 {m}월 실제(Actual)")
                        st.dataframe(m_actual, use_container_width=True, height=400)
    else:
        st.info("2단계에서 '데이터 정제 실행' 버튼을 먼저 눌러주세요.")
