import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta

# --- 1. 데이터베이스 초기화 (중복 방지 로직 포함) ---
def init_db():
    conn = sqlite3.connect('prime_nurse_system.db')
    c = conn.cursor()
    # 간호사 마스터 정보
    c.execute('''CREATE TABLE IF NOT EXISTS nurses (
                    name TEXT PRIMARY KEY, 
                    unit TEXT, 
                    sub_count INTEGER DEFAULT 0,
                    last_d_dedicated TEXT, 
                    visited_wards TEXT)''')
    # 근무 및 실적 로그 (날짜+이름 유니크 설정으로 중복 저장 방지)
    c.execute('''CREATE TABLE IF NOT EXISTS assignment_logs (
                    date TEXT, 
                    name TEXT, 
                    plan_ward TEXT, 
                    actual_ward TEXT,
                    shift TEXT, 
                    status TEXT, 
                    UNIQUE(date, name))''')
    conn.commit()
    conn.close()

# --- 2. 초강력 날짜 확장 엔진 (NoneType 에러 방어) ---
def safe_expand_dates(date_str, year):
    """날짜 형식이 불완전해도 최대한 해석하고 실패 시 빈 리스트 반환"""
    if pd.isna(date_str) or '~' not in str(date_str):
        return []
    try:
        # 숫자, ~, / 외의 불필요한 문자 제거
        clean_str = re.sub(r'[^0-9~/]', '', str(date_str))
        parts = clean_str.split('~')
        if len(parts) < 2: return []

        # 시작 날짜 추출
        s_nums = re.findall(r'\d+', parts[0])
        if len(s_nums) < 2: return []
        s_date = datetime(year, int(s_nums[0]), int(s_nums[1]))

        # 종료 날짜 추출
        e_nums = re.findall(r'\d+', parts[1])
        if not e_nums: return []
        e_month = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_day = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        
        e_date = datetime(year, e_month, e_day)
        # 연말~연초 걸치는 경우 보정
        if e_date < s_date: e_date = e_date.replace(year=year+1)
            
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except:
        return []

# --- 3. 데이터 정제 및 분석 엔진 ---
def robust_analyze(up_p, up_a, year, month_int):
    # 분석에서 제외할 명단 (서무 업무자 등)
    exclude_list = ['고정민']
    
    # [계획표 분석]
    p_sheets = pd.read_excel(up_p, sheet_name=None)
    plan_list = []
    for _, df in p_sheets.items():
        # 열 위치 자동 검색 (상위 15줄 스캔)
        shift_idx, date_cols = -1, []
        for i in range(min(15, len(df))):
            row_vals = df.iloc[i].astype(str).tolist()
            for j, val in enumerate(row_vals):
                if '근무조' in val: shift_idx = j
                if '~' in val: date_cols.append(j)
            if shift_idx != -1 and date_cols: break
        
        if shift_idx == -1: shift_idx = 1
        
        curr_shift = "D"
        for _, row in df.iterrows():
            # D4(단축근무) 포함하여 D/E 업데이트
            s_val = str(row.iloc[shift_idx]).upper()
            if 'D' in s_val: curr_shift = "D"
            elif 'E' in s_val: curr_shift = "E"
            
            for c_idx in date_cols:
                cell_text = str(row.iloc[c_idx])
                # '병동\n이름' 패턴 매칭
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell_text)
                if match:
                    name = match.group(2)
                    if name in exclude_list: continue
                    
                    # 헤더 또는 셀에서 날짜 구간 추출
                    date_header = str(df.columns[c_idx])
                    dates = safe_expand_dates(date_header if '~' in date_header else cell_text, year)
                    for d in dates:
                        plan_list.append({
                            'name': name, 'date': d.strftime('%Y-%m-%d'), 
                            'plan_ward': match.group(1), 'shift': curr_shift
                        })

    # [실제근무표 분석]
    a_sheets = pd.read_excel(up_a, sheet_name=None)
    actual_list = []
    for _, df in a_sheets.items():
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', ''] or name in exclude_list: continue
            
            for d_idx in day_cols:
                day_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not day_match: continue
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward = re.search(r'/(\d+)', code)
                    if ward:
                        actual_list.append({
                            'name': name, 
                            'date': datetime(year, month_int, int(day_match[0])).strftime('%Y-%m-%d'),
                            'actual_ward': str(int(ward.group(1)))
                        })

    # [병합 및 결과 반환]
    df_p, df_a = pd.DataFrame(plan_list), pd.DataFrame(actual_list)
    if df_p.empty or df_a.empty: return pd.DataFrame()
    
    merged = pd.merge(df_a, df_p, on=['name', 'date'], how='left')
    merged['status'] = merged.apply(lambda r: "지원(순환)" if r['actual_ward'] == r['plan_ward'] else "결원대체", axis=1)
    return merged

# --- 4. 메인 UI ---
st.set_page_config(page_title="프라임 매니저", layout="wide")
init_db()

st.title("🏥 프라임 팀 스마트 운영 시스템")
st.sidebar.header("📅 분석 설정")
year = st.sidebar.selectbox("연도", [2026, 2027])
month_text = st.sidebar.select_slider("월", [f"{i}월" for i in range(1, 13)])
month_int = int(re.findall(r'\d+', month_text)[0])

c1, c2 = st.columns(2)
with c1: up_p = st.file_uploader("1. 대기배정표(Plan)", type="xlsx")
with c2: up_a = st.file_uploader("2. 실제근무표(Actual)", type="xlsx")

if up_p and up_a:
    try:
        with st.spinner('데이터를 정제하는 중입니다...'):
            df_result = robust_analyze(up_p, up_a, year, month_int)
        
        if not df_result.empty:
            st.success(f"✅ {year}년 {month_int}월 분석 완료")
            st.dataframe(df_result, use_container_width=True)
            
            # 저장 버튼 등 후속 로직 위치
            if st.button("💾 이력을 DB에 저장"):
                st.balloons()
        else:
            st.warning("매칭된 데이터가 없습니다. 성함이나 날짜 형식을 확인해주세요.")
            
    except Exception as e:
        st.error(f"⚠️ 정제 중 오류 발생: {e}")
