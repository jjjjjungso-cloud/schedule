import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- UI 설정 ---
st.set_page_config(page_title="프라임 데이터 정제 및 검증", layout="wide")

# --- 세션 상태 초기화 (탭 간 데이터 공유용) ---
if 'df_plan_final' not in st.session_state:
    st.session_state.df_plan_final = pd.DataFrame()
if 'df_actual_final' not in st.session_state:
    st.session_state.df_actual_final = pd.DataFrame()

# --- 유틸리티 함수: 실제 근무표 정제 ---
def clean_actual_data(uploaded_file, year, month_int, exclude_names=[]):
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '', 'None'] or name in exclude_names:
                continue
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        shift = 'D' if ('D4' in code or 'D' in code) else 'E'
                        try:
                            # 실제 근무표에서도 평일만 필터링하고 싶다면 여기서 요일 체크 가능
                            date_obj = datetime(year, month_int, int(d_match[0]))
                            if date_obj.weekday() < 5: # 평일만 추가
                                actual_list.append({
                                    '날짜': date_obj.strftime('%Y-%m-%d'),
                                    '주차': f"{date_obj.isocalendar().week}주차",
                                    '성함': name,
                                    '근무조': shift,
                                    '병동': str(int(ward_match.group(1)))
                                })
                        except: continue
    return pd.DataFrame(actual_list)

# --- 유틸리티 함수: 배정표(계획) 펼치기 (평일 & 주차 로직 추가) ---
def expand_plan_data(df):
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    if not all(col in df.columns for col in required):
        return pd.DataFrame()

    for _, row in df.iterrows():
        try:
            start_date = pd.to_datetime(row['시작일'])
            end_date = pd.to_datetime(row['종료일'])
            current_date = start_date
            while current_date <= end_date:
                # 평일 로직: 0(월) ~ 4(금) 사이인 경우만 데이터 생성
                if current_date.weekday() < 5:
                    expanded_list.append({
                        '날짜': current_date.strftime('%Y-%m-%d'),
                        '주차': f"{current_date.isocalendar().week}주차",
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
selected_month_str = st.sidebar.selectbox("대상 월", month_list, index=2)
selected_month_int = int(re.findall(r'\d+', selected_month_str)[0])

# --- 단계별 탭 구성 (3단계 추가) ---
tab1, tab2, tab3 = st.tabs(["📂 1단계: 파일 업로드", "🔍 2단계: 데이터 정제 및 변환", "📊 3단계: 병동 지원 현황 분석"])

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
        st.markdown("### 2. 정제된 데이터 확인 (평일 기준)")
        if st.button("🚀 데이터 정제 및 매칭 실행"):
            # 정제 결과를 세션 스테이트에 저장
            st.session_state.df_plan_final = expand_plan_data(df_p_raw)
            st.session_state.df_actual_final = clean_actual_data(file_a, selected_year, selected_month_int)
            st.success("✅ 데이터 정제가 완료되었습니다.")

        if not st.session_state.df_plan_final.empty:
            col_res_p, col_res_a = st.columns(2)
            with col_res_p:
                st.subheader("📋 정제된 배정표(계획)")
                st.dataframe(st.session_state.df_plan_final, use_container_width=True)
            with col_res_a:
                st.subheader("📋 정제된 근무표(실제)")
                st.dataframe(exp_matrix, use_container_width=True)
    else:
        st.warning("먼저 1단계 탭에서 두 파일을 모두 업로드해주세요.")

with tab3:
    if not st.session_state.df_plan_final.empty:
        df_p = st.session_state.df_plan_final
        st.header("📊 주차별 및 병동별 경험 분석")
        st.info("평일(월~금) 데이터만 반영된 결과입니다.")

        # --- 1. 주차별 현황 ---
        st.subheader("📅 주차별 배정 현황 (누가 어디 있었나?)")
        # 피벗 테이블을 이용해 주차별로 간호사들이 어느 병동에 있었는지 요약
        weekly_pivot = df_p.pivot_table(index='성함', columns='주차', values='병동', aggfunc=lambda x: ", ".join(set(x)))
        st.dataframe(weekly_pivot, use_container_width=True)

        # --- 2. 병동 경험 이력 추적 ---
        st.markdown("---")
        st.subheader("🕵️‍♀️ 간호사별 병동 경험 매트릭스")
        
        # 간호사가 각 병동을 몇 번 지원 나갔는지 카운트
        exp_matrix = df_p.groupby(['성함', '병동']).size().unstack(fill_value=0)
        st.write("표 안의 숫자는 해당 병동 방문 일수(Day)입니다.")
        st.dataframe(exp_matrix.style.background_gradient(cmap='Blues'), use_container_width=True)

        # --- 3. 우선순위 파악 (미방문 병동) ---
        st.markdown("---")
        st.subheader("🎯 다음 달 배정 우선순위 참고")
        
        selected_nurse = st.selectbox("간호사 선택", df_p['성함'].unique())
        if selected_nurse:
            visited = set(df_p[df_p['성함'] == selected_nurse]['병동'].unique())
            all_wards = set(df_p['병동'].unique())
            not_visited = all_wards - visited
            
            c1, c2 = st.columns(2)
            c1.success(f"✅ **{selected_nurse}** 간호사 경험 병동: {', '.join(sorted(visited))}")
            if not_visited:
                c2.warning(f"⚠️ **아직 안 가본 병동**: {', '.join(sorted(not_visited))}")
            else:
                c2.info("👏 모든 병동을 경험했습니다!")
    else:
        st.info("2단계에서 '데이터 정제 및 매칭 실행' 버튼을 눌러주세요.")
