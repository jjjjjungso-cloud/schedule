import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 데이터 처리 엔진 (Logic) ---
class NursingDataEngine:
    def __init__(self, year=2026):
        self.year = year

    def parse_work_cell(self, val):
        """P-D4/116 같은 셀 데이터를 (근무, 병동)으로 분리"""
        val = str(val).strip()
        # 휴무 키워드 처리
        off_keywords = ['건', '필', 'ET', '/', 'nan', 'None', '']
        if not val.startswith('P-') and any(k in val for k in off_keywords):
            return "OFF", None
        
        # 정규식: P- 뒤의 첫 알파벳(D, E 등)과 / 뒤의 숫자(병동) 추출
        # D4, D6 등 숫자가 붙어도 첫 글자만 가져옴
        match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
        if match:
            shift = match.group(1).upper()
            ward = match.group(2)
            return shift, ward
        return "OFF", None

    def expand_date_range(self, date_str):
        """'3/3~3/13' 형태의 문자열을 개별 날짜 리스트로 변환"""
        try:
            start_str, end_str = date_str.split('~')
            start_m, start_d = map(int, start_str.split('/'))
            end_m, end_d = map(int, end_str.split('/'))
            
            start_date = datetime(self.year, start_m, start_d)
            end_date = datetime(self.year, end_m, end_d)
            
            date_list = []
            curr = start_date
            while curr <= end_date:
                date_list.append(curr.strftime('%Y-%m-%d'))
                curr += timedelta(days=1)
            return date_list
        except:
            return []

    def process_actual_data(self, df, month_name):
        """실제 근무표 정규화 (4-5월 열 기반)"""
        rows = []
        # C열(이름)은 index 2, H열(날짜 시작)은 index 7 가정
        for _, row in df.iterrows():
            name = str(row.iloc[2]).strip()
            if name == 'nan' or not name: continue
            
            for col_idx in range(7, len(df.columns)):
                day_val = str(df.columns[col_idx]).replace('일', '').strip()
                if not day_val.isdigit(): continue
                
                cell_val = row.iloc[col_idx]
                shift, ward = self.parse_work_cell(cell_val)
                
                if shift != "OFF":
                    month_num = month_name.replace('월', '')
                    date_str = f"{self.year}-{month_num.zfill(2)}-{day_val.zfill(2)}"
                    rows.append([name, date_str, shift, ward, 'Actual'])
        return pd.DataFrame(rows, columns=['성함', '날짜', '근무', '병동', '구분'])

    def process_march_data(self, df):
        """3월 근무표 정규화 (기간 기반)"""
        rows = []
        for _, row in df.iterrows():
            name = str(row.iloc[2]).strip()
            # 행에서 '3/3~3/13' 같은 패턴 찾기
            for cell in row:
                cell_str = str(cell)
                if '~' in cell_str and '/' in cell_str:
                    dates = self.expand_date_range(cell_str)
                    # 해당 행의 근무조 정보 찾기 (예: D, E)
                    shift_info = "D" if "D" in str(row.iloc[3]) else "E" 
                    # 임의의 병동 데이터 (실제 구조에 맞춰 index 조정 필요)
                    ward_info = str(row.iloc[4]) 
                    
                    for d in dates:
                        rows.append([name, d, shift_info, ward_info, 'Actual'])
        return pd.DataFrame(rows, columns=['성함', '날짜', '근무', '병동', '구분'])

# --- 2. Streamlit UI ---
st.set_page_config(page_title="프라임 간호사 데이터 통합 시스템", layout="wide")
st.title("🏥 프라임 간호사 근무 데이터 통합 분석")

# 사이드바 설정
st.sidebar.header("📅 분석 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("대상 월", [f"{i}월" for i in range(1, 13)], index=3)

engine = NursingDataEngine(year=selected_year)

# 파일 업로드
col1, col2 = st.columns(2)
with col1:
    file_p = st.file_uploader("1️⃣ 배정표(Plan) 업로드", type="xlsx")
with col2:
    file_a = st.file_uploader("2️⃣ 근무표(Actual) 업로드", type="xlsx")

if file_a:
    xl_a = pd.ExcelFile(file_a)
    sheet_a = st.selectbox("실제 근무 시트 선택", xl_a.sheet_names)
    df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)

    # 월별 맞춤 프로세싱
    if "3월" in selected_month:
        df_actual_std = engine.process_march_data(df_a_raw)
    else:
        df_actual_std = engine.process_actual_data(df_a_raw, selected_month)

    st.subheader(f"📊 {selected_month} 정제 데이터 (표준 포맷)")
    st.dataframe(df_actual_std, use_container_width=True)

    # 주차별 통계 기능
    if not df_actual_std.empty:
        df_actual_std['날짜'] = pd.to_datetime(df_actual_std['날짜'])
        df_actual_std['주차'] = df_actual_std['날짜'].dt.isocalendar().week
        
        st.divider()
        st.subheader("🗓️ 주차별 지원 현황")
        week_stats = df_actual_std.groupby(['주차', '병동']).size().unstack().fillna(0)
        st.bar_chart(week_stats)

if file_p and file_a:
    if st.button("🚀 계획 대비 실제 근무 정합성 분석 시작"):
        st.success("데이터 병합 및 분석 로직 가동 중...")
        # 여기에 계획표 표준화(standardize_plan) 및 merge 로직 추가 가능
