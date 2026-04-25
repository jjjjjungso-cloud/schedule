import streamlit as st

import pandas as pd

import re

from datetime import datetime, timedelta



# --- UI 설정 ---

st.set_page_config(page_title="프라임 데이터 정제 및 검증", layout="wide")



# --- 유틸리티 함수: 실제 근무표 정제 (사용자 제공 로직 기반) ---

def clean_actual_data(uploaded_file, year, month_int, exclude_names=[]):

    """근무표 정제: P- 코드 분석 및 날짜별 데이터 변환"""

    # 전체 시트를 읽어오기 위해 ExcelFile 사용

    xl = pd.ExcelFile(uploaded_file)

    actual_list = []

    

    for sheet_name in xl.sheet_names:

        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)

        

        # 이름 열 찾기 (보통 '명' 또는 '성명' 포함)

        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)

        # '일'이 들어간 날짜 열들 찾기

        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]

        

        for _, row in df.iterrows():

            name = str(row.iloc[name_idx]).strip()

            if name in ['nan', '명', '', 'None'] or name in exclude_names:

                continue

                

            for d_idx in day_cols:

                # 열 제목에서 숫자(일)만 추출

                d_match = re.findall(r'\d+', str(df.columns[d_idx]))

                if not d_match: continue

                

                code = str(row.iloc[d_idx])

                # 'P-'로 시작하는 데이터만 필터링

                if code.startswith('P-'):

                    ward_match = re.search(r'/(\d+)', code)

                    if ward_match:

                        # D4 코드인 경우 D근무로 인정, 그 외 E 등 구분

                        shift = 'D' if ('D4' in code or 'D' in code) else 'E'

                        try:

                            date_val = datetime(year, month_int, int(d_match[0])).strftime('%Y-%m-%d')

                            actual_list.append({

                                '날짜': date_val,

                                '성함': name,

                                '근무조': shift,

                                '병동': str(int(ward_match.group(1)))

                            })

                        except ValueError: # 31일이 없는 달 등 예외 처리

                            continue

                            

    return pd.DataFrame(actual_list)



# --- 유틸리티 함수: 배정표(계획) 펼치기 ---

def expand_plan_data(df):

    """시작일~종료일 범위를 하루 단위 행으로 분리"""

    expanded_list = []

    # 필수 컬럼 체크

    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']

    if not all(col in df.columns for col in required):

        return pd.DataFrame()



    for _, row in df.iterrows():

        try:

            start_date = pd.to_datetime(row['시작일'])

            end_date = pd.to_datetime(row['종료일'])

            

            # 날짜 범위 생성

            current_date = start_date

            while current_date <= end_date:

                expanded_list.append({

                    '날짜': current_date.strftime('%Y-%m-%d'),

                    '성함': str(row['간호사 성함']).strip(),

                    '근무조': row['근무조'],

                    '병동': str(row['배정병동'])

                })

                current_date += timedelta(days=1)

        except:

            continue

            

    return pd.DataFrame(expanded_list)



# --- 메인 대시보드 ---

st.title("🏥 프라임 데이터 입력 및 정합성 검증")



# 사이드바: 설정

st.sidebar.header("📅 분석 기준 설정")

selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)

month_list = [f"{i}월" for i in range(1, 13)]

selected_month_str = st.sidebar.selectbox("대상 월", month_list, index=2) # 3월 기본

selected_month_int = int(re.findall(r'\d+', selected_month_str)[0])



# --- 단계별 탭 구성 ---

tab1, tab2 = st.tabs(["📂 1단계: 파일 업로드", "🔍 2단계: 데이터 정제 및 변환"])



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

        if file_a:

            st.success("근무표 로드 완료")



with tab2:

    if file_p and file_a:

        st.markdown("### 2. 정제된 데이터 확인")

        st.info("업로드된 데이터를 '날짜-성함-근무조-병동'의 동일한 형식으로 변환한 결과입니다.")

        

        # 변환 실행 버튼

        if st.button("🚀 데이터 정제 및 매칭 실행"):

            # 1. 배정표 정제

            df_plan_final = expand_plan_data(df_p_raw)

            # 2. 근무표 정제 (사용자 함수 적용)

            df_actual_final = clean_actual_data(file_a, selected_year, selected_month_int)



            col_res_p, col_res_a = st.columns(2)



            with col_res_p:

                st.subheader("📋 정제된 배정표(계획)")

                if not df_plan_final.empty:

                    st.dataframe(df_plan_final, use_container_width=True, height=400)

                    st.caption(f"총 {len(df_plan_final)}건의 계획 데이터가 생성되었습니다.")

                else:

                    st.error("배정표 형식이 맞지 않습니다. 컬럼명을 확인하세요.")



            with col_res_a:

                st.subheader("📋 정제된 근무표(실제)")

                if not df_actual_final.empty:

                    st.dataframe(df_actual_final, use_container_width=True, height=400)

                    st.caption(f"총 {len(df_actual_final)}건의 실제 근무 데이터(P-코드)가 추출되었습니다.")

                else:

                    st.warning("실제 근무표에서 'P-' 코드를 찾을 수 없습니다.")

            

            st.divider()

            st.success("✅ 데이터 정제가 완료되었습니다. 이제 두 테이블을 비교하여 정합성을 분석할 수 있습니다.")

    else:

        st.warning("먼저 1단계 탭에서 두 파일을 모두 업로드해주세요.") 이 코드의 다음단계에서 월별로 탭을 만들어줄수있어?
