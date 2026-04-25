import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- UI 설정 ---
st.set_page_config(page_title="프라임 데이터 정제 및 검증", layout="wide")

# --- 세션 상태 초기화 (데이터 유지용) ---
if 'df_plan' not in st.session_state: st.session_state.df_plan = None
if 'df_actual' not in st.session_state: st.session_state.df_actual = None

# --- [유틸리티 함수] 실제 근무표 정제 ---
def clean_actual_data(uploaded_file, year, month_int, exclude_names=[]):
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '', 'None'] or name in exclude_names: continue
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        shift = 'D' if ('D4' in code or 'D' in code) else 'E'
                        try:
                            date_val = datetime(year, month_int, int(d_match[0])).strftime('%Y-%m-%d')
                            actual_list.append({
                                '날짜': date_val, '성함': name, '근무조': shift, '병동': str(int(ward_match.group(1)))
                            })
                        except ValueError: continue
    return pd.DataFrame(actual_list)

# --- [유틸리티 함수] 배정표(계획) 펼치기 ---
def expand_plan_data(df):
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    if not all(col in df.columns for col in required): return pd.DataFrame()
    for _, row in df.iterrows():
        try:
            start_date = pd.to_datetime(row['시작일'])
            end_date = pd.to_datetime(row['종료일'])
            current_date = start_date
            while current_date <= end_date:
                expanded_list.append({
                    '날짜': current_date.strftime('%Y-%m-%d'),
                    '성함': str(row['간호사 성함']).strip(),
                    '근무조': row['근무조'],
                    '병동': str(row['배정병동'])
                })
                current_date += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

# --- 메인 대시보드 ---
st.title("🏥 프라임 데이터 입력 및 정합성 검증")

# 사이드바: 설정
st.sidebar.header("📅 분석 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
month_list = [f"{i}월" for i in range(1, 13)]
selected_month_str = st.sidebar.selectbox("대상 월", month_list, index=3) # 기본 4월
selected_month_int = int(re.findall(r'\d+', selected_month_str)[0])

# --- 단계별 탭 구성 ---
tab1, tab2, tab3 = st.tabs(["📂 1단계: 파일 업로드", "🔍 2단계: 데이터 정제 및 변환", "📊 3단계: 지원 근무 현황 요약"])

with tab1:
    st.markdown("### 1. 배정표(계획)와 근무표(실제)를 업로드하세요.")
    col_p, col_a = st.columns(2)
    with col_p:
        st.header("1️⃣ 배정표(계획) 업로드")
        file_p = st.file_uploader("주간 배정표(.xlsx) 선택", type="xlsx", key="plan_up")
        if file_p:
            xl_p = pd.ExcelFile(file_p)
            sheet_p = st.selectbox("분석 시트(계획)", xl_p.sheet_names, key="p_sheet")
            df_p_raw = pd.read_excel(file_p, sheet_name=sheet_p)
            st.success("배정표 로드 완료")
    with col_a:
        st.header("2️⃣ 실제 근무표(Actual) 업로드")
        file_a = st.file_uploader("월간 근무표(.xlsx) 선택", type="xlsx", key="actual_up")
        if file_a: st.success("근무표 로드 완료")

with tab2:
    if file_p and file_a:
        if st.button("🚀 데이터 정제 및 매칭 실행"):
            # 정제 후 세션 스테이트에 저장
            st.session_state.df_plan = expand_plan_data(df_p_raw)
            st.session_state.df_actual = clean_actual_data(file_a, selected_year, selected_month_int)
            st.success("✅ 정제가 완료되었습니다. 3단계 탭에서 요약을 확인하세요.")

        if st.session_state.df_plan is not None:
            col_res_p, col_res_a = st.columns(2)
            with col_res_p:
                st.subheader("📋 정제된 배정표(계획)")
                st.dataframe(st.session_state.df_plan, use_container_width=True)
            with col_res_a:
                st.subheader("📋 정제된 근무표(실제)")
                st.dataframe(st.session_state.df_actual, use_container_width=True)
    else:
        st.warning("먼저 1단계 탭에서 파일을 업로드해주세요.")

with tab3:
    if st.session_state.df_actual is not None and not st.session_state.df_actual.empty:
        df_act = st.session_state.df_actual
        
        st.header(f"📊 {selected_month_str} 지원 근무 현황 요약")
        
        # 상단 요약 카드
        c1, c2, c3 = st.columns(3)
        c1.metric("총 지원 근무 건수", f"{len(df_act)}건")
        c2.metric("지원 투입 간호사 수", f"{df_act['성함'].nunique()}명")
        c3.metric("대상 병동 수", f"{df_act['병동'].nunique()}개소")

        st.markdown("---")

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("👤 간호사별 지원 나간 병동")
            # 간호사별/병동별 그룹화
            nurse_summary = df_act.groupby(['성함', '병동']).size().reset_index(name='횟수')
            st.dataframe(nurse_summary, use_container_width=True, height=400)

        with col_right:
            st.subheader("🏥 병동별 지원 받은 횟수")
            ward_summary = df_act.groupby('병동').size().reset_index(name='총 지원받은 횟수')
            st.bar_chart(data=ward_summary.set_index('병동'))

        st.subheader("📅 날짜별 상세 지원 내역")
        st.table(df_act.sort_values(by='날짜'))
    else:
        st.info("2단계에서 '데이터 정제 및 매칭 실행' 버튼을 먼저 눌러주세요.")
