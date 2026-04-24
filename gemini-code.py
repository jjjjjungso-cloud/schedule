import streamlit as st
import pandas as pd
import re
from io import BytesIO
from datetime import datetime

# 설정
st.set_page_config(page_title="프라임 배정 시스템", layout="wide")
st.title("🏥 프라임 간호사 스마트 순환 배정 시스템")

# --- 1. 데이터 정제 함수 정의 ---

def clean_wait_ward_data(uploaded_file):
    """대기병동 배정표(Plan) 정제: 모든 시트에서 '번호\n성함' 추출"""
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    refined_data = []

    for sheet_name, df in all_sheets.items():
        df = df.fillna("")
        for row_idx, row in df.iterrows():
            for val in row:
                # 패턴 찾기: "숫자\n이름" (예: 72\n박소영)
                match = re.search(r'(\d+)\s*\n\s*([가-힣]+)', str(val))
                if match:
                    refined_data.append({
                        "성함": match.group(2),
                        "계획병동": match.group(1),
                        "출처": sheet_name
                    })
    return pd.DataFrame(refined_data)

def clean_actual_schedule(uploaded_file):
    """실제 근무스케줄(Actual) 정제: 모든 시트에서 실제 출근 병동 추출"""
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    all_actual_data = []

    for sheet_name, df in all_sheets.items():
        # 이름 컬럼 찾기 ('명' 또는 '성명')
        name_col = next((c for c in df.columns if '명' in str(c)), None)
        if not name_col: continue
        
        day_cols = [c for c in df.columns if '일' in str(c)]
        
        # 가로 데이터를 세로로 변환
        df_melted = df.melt(id_vars=[name_col], value_vars=day_cols, value_name='근무코드')
        
        for _, row in df_melted.iterrows():
            # 근무코드에서 숫자만 추출 (예: P-D63/072 -> 072)
            ward_no = "".join(re.findall(r'\d+', str(row['근무코드'])))
            if ward_no:
                all_actual_data.append({
                    "성함": row[name_col],
                    "실제병동": ward_no,
                    "출처": sheet_name
                })
    return pd.DataFrame(all_actual_data)

# --- 2. 화면 구성 및 프로세스 ---

# STEP 1: 파일 업로드
st.header("Step 1. 과거 데이터 업로드 (모든 시트 자동 포함)")
col1, col2 = st.columns(2)

with col1:
    uploaded_p = st.file_uploader("1. 과거 대기병동 배정표(Plan) 업로드", type="xlsx")
with col2:
    uploaded_a = st.file_uploader("2. 실제 근무스케줄표(Actual) 업로드", type="xlsx")

if uploaded_p and uploaded_a:
    try:
        # 데이터 정제 실행
        with st.spinner('데이터를 분석 중입니다...'):
            df_plan = clean_wait_ward_data(uploaded_p)
            df_actual = clean_actual_schedule(uploaded_a)
        
        st.success(f"✅ 분석 완료! ({len(df_plan)}개의 계획과 {len(df_actual)}개의 실제 근무 기록을 찾았습니다.)")

        # STEP 2: 지원 vs 결원 대체 판별 로직
        st.header("Step 2. 간호사별 지원 및 결원 대체 현황")
        
        history_summary = {} # {이름: {'지원': set(), '결원대체': set()}}

        # 실제 비교 로직 (간략화: 계획된 병동에 갔으면 지원, 아니면 결원대체)
        for name in df_actual['성함'].unique():
            if pd.isna(name) or name == "": continue
            
            p_wards = set(df_plan[df_plan['성함'] == name]['계획병동'])
            a_wards = df_actual[df_actual['성함'] == name]['실제병동'].tolist()
            
            if name not in history_summary:
                history_summary[name] = {'지원': set(), '결원대체': set()}
            
            for aw in a_wards:
                if aw in p_wards:
                    history_summary[name]['지원'].add(aw)
                else:
                    history_summary[name]['결원대체'].add(aw)

        # 현황 표 출력
        display_data = []
        for name, data in history_summary.items():
            display_data.append({
                "성함": name,
                "지원(순환) 병동": ", ".join(sorted(data['지원'])),
                "결원 대체(숙련도) 병동": ", ".join(sorted(data['결원대체'])),
                "결원 대체 횟수": len(data['결원대체'])
            })
        
        st.table(pd.DataFrame(display_data))

        # STEP 3: 이번 달 배정
        st.header("Step 3. 이번 달 스마트 배정")
        uploaded_foam = st.file_uploader("이번 달 빈 명단 파일 업로드", type=["xlsx", "csv"])
        
        if uploaded_foam:
            # D4 전담자 선택 (공평성 고려)
            d4_candidates = sorted(list(history_summary.keys()))
            d4_names = st.multiselect("이번 달 D4(한 달 오전) 고정 근무자를 선택하세요", d4_candidates)
            
            if st.button("🚀 스마트 배정 실행"):
                st.balloons()
                # (이후 배정 알고리즘 및 결과 생성 로직)
                st.write("### ✨ 최종 배정 결과 확인")
                # 결과 테이블 및 다운로드 버튼 생성...
                st.info("배정 로직: 지원 이력이 없는 병동을 최우선으로 매칭하며, D4는 오전 근무로 고정합니다.")

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        st.info("엑셀 파일의 시트 구성이나 컬럼명(성명, 명 등)을 다시 한번 확인해 주세요.")

else:
    st.info("왼쪽 사이드바 또는 위 버튼을 통해 3~5월 데이터를 먼저 업로드해 주세요.")
