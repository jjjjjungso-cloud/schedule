import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta

# --- 1. DB 초기화 ---
def init_db():
    conn = sqlite3.connect('prime_nurse_system.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS nurses (
                    name TEXT PRIMARY KEY, unit TEXT, sub_count INTEGER DEFAULT 0,
                    last_d_dedicated TEXT, visited_wards TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS assignment_logs (
                    date TEXT, name TEXT, plan_ward TEXT, actual_ward TEXT,
                    shift TEXT, status TEXT, UNIQUE(date, name))''')
    conn.commit()
    conn.close()

# --- 2. 초강력 데이터 정제 엔진 ---

def safe_expand_dates(date_str, year):
    """'3/30~4/10' 형태를 개별 날짜로 변환 (실패 시 빈 리스트 반환)"""
    if pd.isna(date_str) or '~' not in str(date_str): return []
    try:
        clean_str = re.sub(r'[^0-9~]', '', str(date_str))
        parts = clean_str.split('~')
        s_nums = re.findall(r'\d+', parts[0])
        s_date = datetime(year, int(s_nums[0]), int(s_nums[1]))
        e_nums = re.findall(r'\d+', parts[1])
        e_month = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_day = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        e_date = datetime(year, e_month, e_day)
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except: return []

def clean_plan_data(uploaded_file, year, exclude_names):
    """핀셋 로직: 불필요한 구역/명단 제외하고 [병동+이름]만 추출"""
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    plan_list = []
    for _, df in all_sheets.items():
        shift_idx, date_cols = -1, []
        for i in range(min(10, len(df))): # 상위 10줄 스캔
            row_vals = df.iloc[i].astype(str).tolist()
            for j, val in enumerate(row_vals):
                if '근무조' in val: shift_idx = j
                if '~' in val and j not in date_cols: date_cols.append(j)
        for j, col in enumerate(df.columns):
            if '~' in str(col) and j not in date_cols: date_cols.append(j)
        
        if shift_idx == -1: shift_idx = 1
        curr_shift = "D"
        for idx, row in df.iterrows():
            s_val = str(row.iloc[shift_idx]).upper()
            if 'D' in s_val: curr_shift = "D"
            elif 'E' in s_val: curr_shift = "E"
            for c_idx in date_cols:
                cell_text = str(row.iloc[c_idx])
                # [병동번호] + [이름] 패턴 핀셋 추출
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell_text)
                if match:
                    ward, name = match.group(1), match.group(2)
                    if name in exclude_names: continue
                    date_header = str(df.columns[c_idx])
                    dates = safe_expand_dates(date_header if '~' in date_header else cell_text, year)
                    for d in dates:
                        plan_list.append({
                            '날짜': d.strftime('%Y-%m-%d'), 
                            '성함': name, 
                            '계획병동': ward, # '대기병동' 대신 '계획병동'으로 통일
                            '근무조': curr_shift
                        })
    return pd.DataFrame(plan_list)

def clean_actual_data(uploaded_file, year, month_int, exclude_names):
    """근무표 정제: P- 코드 분석 (D4 포함)"""
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    actual_list = []
    for _, df in all_sheets.items():
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', ''] or name in exclude_names: continue
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        # D4 및 D는 D로 인식
                        shift = 'D' if any(x in code for x in ['D', 'D4']) else 'E'
                        actual_list.append({
                            '날짜': datetime(year, month_int, int(d_match[0])).strftime('%Y-%m-%d'),
                            '성함': name, '실제병동': str(int(ward_match.group(1))), '근무조': shift
                        })
    return pd.DataFrame(actual_list)

# --- 3. UI 구성 ---

st.set_page_config(page_title="프라임 매니저", layout="wide")
init_db()

st.title("🏥 프라임 간호사 스마트 관리 시스템")
st.sidebar.header("🔍 분석 단계 선택")

step = st.sidebar.radio("작업 선택", ["1. 배정표(Plan) 검증", "2. 근무표(Actual) 검증", "3. 통합 비교 분석"])
selected_year = st.sidebar.selectbox("연도 설정", [2026, 2027], index=0)
exclude_names = ['고정민']

# Step 1: 배정표 검증
if step == "1. 배정표(Plan) 검증":
    st.header("📋 대기배정표(Plan) 데이터 추출")
    up_p = st.file_uploader("배정표 업로드", type="xlsx")
    if up_p:
        df_plan = clean_plan_data(up_p, selected_year, exclude_names)
        if not df_plan.empty:
            st.success(f"✅ {len(df_plan)}개의 일별 데이터를 추출했습니다.")
            st.dataframe(df_plan, use_container_width=True)
        else: st.warning("데이터를 찾지 못했습니다. 셀의 [병동번호+이름] 형식을 확인하세요.")

# Step 2: 근무표 검증
elif step == "2. 근무표(Actual) 검증":
    st.header("📅 실제 근무표(Actual) 정제")
    up_a = st.file_uploader("근무표 업로드", type="xlsx")
    sel_month = st.sidebar.selectbox("해당 월 선택", [f"{i}월" for i in range(1, 13)])
    month_int = int(re.findall(r'\d+', sel_month)[0])
    if up_a:
        df_actual = clean_actual_data(up_a, selected_year, month_int, exclude_names)
        if not df_actual.empty:
            st.success(f"✅ {len(df_actual)}개의 근무 데이터를 정제했습니다.")
            st.dataframe(df_actual, use_container_width=True)
        else: st.warning("P- 코드를 찾지 못했습니다.")

# Step 3: 통합 비교 분석
elif step == "3. 통합 비교 분석":
    st.header("⚖️ 계획 vs 실제 통합 분석")
    c1, c2 = st.columns(2)
    with c1: up_p = st.file_uploader("배정표 업로드", type="xlsx", key="p3")
    with c2: up_a = st.file_uploader("근무표 업로드", type="xlsx", key="a3")
    sel_month = st.sidebar.selectbox("해당 월 선택", [f"{i}월" for i in range(1, 13)], key="m3")
    month_int = int(re.findall(r'\d+', sel_month)[0])

    if up_p and up_a:
        df_p = clean_plan_data(up_p, selected_year, exclude_names)
        df_a = clean_actual_data(up_a, selected_year, month_int, exclude_names)
        
        if not df_p.empty and not df_a.empty:
            # 날짜와 성함 기준 병합 (계획병동 컬럼명 주의!)
            merged = pd.merge(df_a, df_p, on=['날짜', '성함'], how='left', suffixes=('', '_계획'))
            
            def check_status(row):
                if pd.isna(row['계획병동']): return "기타(로그없음)"
                return "지원(순환)" if row['실제병동'] == row['계획병동'] else "결원대체"
            
            merged['상태'] = merged.apply(check_status, axis=1)
            
            st.subheader("📊 이번 달 운영 결과 요약")
            summary = merged.groupby(['성함', '상태']).size().unstack(fill_value=0)
            st.table(summary)
            
            with st.expander("🔍 상세 내역 보기"):
                st.dataframe(merged[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']], use_container_width=True)
        else:
            st.error("데이터 정제에 실패했습니다. 1단계와 2단계를 먼저 확인해주세요.")
