import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="프라임 배정 시스템", layout="wide")
st.title("🏥 프라임 간호사 스마트 순환 배정 시스템")

# --- STEP 1: 데이터 로드 및 전처리 ---
st.header("Step 1. 과거 데이터 업로드 (계획 vs 실제)")
col1, col2 = st.columns(2)

with col1:
    uploaded_plan = st.file_uploader("1. 과거 대기병동 배정표(계획) 업로드", type=["xlsx", "csv"])
with col2:
    uploaded_actual = st.file_uploader("2. 실제 근무스케줄표(결과) 업로드", type=["xlsx", "csv"])

def extract_ward_number(text):
    """'P-D63/072' 또는 '72\n박소영'에서 숫자만 추출"""
    found = re.findall(r'\d+', str(text))
    return found[0] if found else ""

if uploaded_plan and uploaded_actual:
    try:
        # 데이터 읽기 (제목줄 위치 고려)
        df_p = pd.read_csv(uploaded_plan) if uploaded_plan.name.endswith('.csv') else pd.read_excel(uploaded_plan)
        df_a = pd.read_csv(uploaded_actual) if uploaded_actual.name.endswith('.csv') else pd.read_excel(uploaded_actual)

        # '성명' 또는 '명' 컬럼 찾기
        name_col_a = '명' if '명' in df_a.columns else '성명'
        
        st.success("✅ 파일 로드 및 구조 분석 완료!")

        # --- STEP 2: 현황 분석 로직 ---
        st.header("Step 2. 지원 vs 결원대체 분석 결과")
        
        history = {} # {이름: {'지원': set(), '결원대체': set()}}

        # 실제 분석 수행 (간략화된 로직)
        for _, row in df_a.iterrows():
            name = row[name_col_a]
            if pd.isna(name) or name == '성명': continue
            
            if name not in history:
                history[name] = {'지원': set(), '결원대체': set()}
            
            # 모든 날짜(1일~31일)를 돌며 실제 근무지 확인
            for day in range(1, 32):
                day_col = f"{day}일"
                if day_col in df_a.columns:
                    actual_work = extract_ward_number(row[day_col])
                    if actual_work:
                        # 여기에서 계획(df_p)과 비교하여 지원/결원대체 분류
                        # (샘플 로직: 일단 이력에 추가)
                        history[name]['지원'].add(actual_work)

        # 결과 표시
        summary_data = []
        for name, records in history.items():
            summary_data.append({
                "성함": name,
                "방문한 병동(지원)": ", ".join(sorted(records['지원'])),
                "결원 대체 숙련도": ", ".join(sorted(records['결원대체']))
            })
        st.table(pd.DataFrame(summary_data))

        # --- STEP 3: 이번 달 배정 ---
        st.header("Step 3. 이번 달 스마트 배정")
        uploaded_foam = st.file_uploader("이번 달 빈 명단 파일 업로드", type=["xlsx", "csv"])
        
        if uploaded_foam:
            # D4 전담자 선택
            d4_names = st.multiselect("이번 달 D4(한 달 오전) 고정 근무자를 선택하세요", list(history.keys()))
            
            if st.button("🚀 배정 실행"):
                # 배정 결과 생성 및 출력 로직...
                st.balloons()
                st.write("### ✨ 최종 배정 결과")
                # 결과 테이블 및 다운로드 버튼 생성

    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")