import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta
import os

# --- 1. 데이터베이스(DB) 설계 및 초기화 ---
def init_db():
    conn = sqlite3.connect('prime_nurse.db')
    c = conn.cursor()
    
    # 간호사 마스터 테이블 (Nurse Table)
    c.execute('''CREATE TABLE IF NOT EXISTS nurses (
                    name TEXT PRIMARY KEY,
                    unit TEXT, -- 1동 또는 2동
                    sub_count INTEGER DEFAULT 0, -- 누적 결원대체 횟수
                    last_d_dedicated TEXT, -- 마지막 한 달 D전담 수행 월
                    visited_wards TEXT -- 방문한 병동 리스트 (JSON/Text)
                )''')
    
    # 배정 및 실적 로그 테이블 (Assignment Log)
    # [이름 + 날짜]를 유니크 키로 설정하여 중복 저장 방지
    c.execute('''CREATE TABLE IF NOT EXISTS assignment_logs (
                    date TEXT,
                    name TEXT,
                    plan_ward TEXT,
                    actual_ward TEXT,
                    shift TEXT, -- D, E, D4 등
                    status TEXT, -- 지원(순환) 또는 결원대체
                    UNIQUE(date, name)
                )''')
    
    # 병동 마스터 테이블 (Ward Table)
    c.execute('''CREATE TABLE IF NOT EXISTS wards (
                    ward_no TEXT PRIMARY KEY,
                    unit TEXT,
                    zone TEXT
                )''')
    
    conn.commit()
    conn.close()

# --- 2. 실무 최적화 데이터 정제 엔진 ---

def clean_ward_code(code):
    """'P-D63/072' 형태에서 슬래시(/) 뒤의 병동 번호 추출"""
    try:
        code_str = str(code)
        match = re.search(r'/(\d+)', code_str)
        if match:
            return str(int(match.group(1))) # '072' -> '72'
        return None
    except:
        return None

def process_shift_code(code):
    """D4(임신 단축)를 일반 D근무로 통합 인식"""
    code_str = str(code).upper()
    if 'D4' in code_str or 'P-D4' in code_str:
        return 'D'
    if 'D' in code_str: return 'D'
    if 'E' in code_str: return 'E'
    return None

# --- 3. Streamlit UI (뼈대 구축) ---

st.set_page_config(page_title="프라임 스마트 관리 시스템", layout="wide")
init_db() # 앱 시작 시 DB 초기화

st.title("🏥 프라임 간호사 스마트 배치 및 이력 관리")
st.markdown("---")

# [UI - 상단] 연도/월 선택 및 파일 업로드 영역
st.sidebar.header("📅 분석 대상 설정")
selected_year = st.sidebar.selectbox("연도 선택", [2026, 2027, 2028, 2029, 2030])
selected_month = st.sidebar.select_slider("월 선택", options=[f"{i}월" for i in range(1, 13)])

st.header("📂 데이터 업로드 및 정제")
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 대기병동 배정표 (Plan)")
    uploaded_plan = st.file_uploader("배정표 엑셀 업로드 (.xlsx)", type="xlsx", key="plan")
    if uploaded_plan:
        st.info("💡 대기병동 배정표가 인식되었습니다.")

with col2:
    st.subheader("2. 실제 근무표 (Actual)")
    uploaded_actual = st.file_uploader("근무표 엑셀 업로드 (.xlsx)", type="xlsx", key="actual")
    if uploaded_actual:
        st.info("💡 실제 근무스케줄표가 인식되었습니다.")

# --- 4. 데이터 정제 결과 미리보기 (뼈대) ---

if uploaded_plan and uploaded_actual:
    st.markdown("---")
    st.header("🔍 정제 데이터 미리보기 (품질 검사)")
    
    # 2단계에서 구현할 알고리즘을 위해 데이터 프레임 로딩 로직 준비
    st.success(f"현재 {selected_year}년 {selected_month} 데이터를 처리할 준비가 되었습니다.")
    
    # 예시: DB에 등록된 간호사 현황 출력 (초기에는 비어있음)
    st.subheader("👥 간호사 이력 현황 (Nurse DB)")
    conn = sqlite3.connect('prime_nurse.db')
    nurses_df = pd.read_sql_query("SELECT * FROM nurses", conn)
    conn.close()
    
    if nurses_df.empty:
        st.warning("현재 DB에 등록된 간호사 정보가 없습니다. 파일 분석을 통해 자동으로 등록됩니다.")
    else:
        st.dataframe(nurses_df, use_container_width=True)

else:
    # 파일을 올리지 않았을 때 보여줄 가이드 이미지나 텍스트
    st.write("위의 두 파일을 모두 업로드하면 '동별 순번제'와 '차기 배정 전략' 분석이 시작됩니다.")

# --- 디자인 포인트 ---
st.sidebar.markdown("---")
st.sidebar.write("최종 목표: 데이터 기반 차기 대기 병동 최적화")
