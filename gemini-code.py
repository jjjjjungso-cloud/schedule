import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta

# --- 1. DB 초기화 및 기본 설정 ---
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

def register_initial_nurses():
    """서무 업무자(고정민)를 제외한 프라임 간호사 13명 등록"""
    nurses = [
        ('정윤정', '1동'), ('최휘영', '1동'), ('기아현', '1동'), ('김유진', '1동'),
        ('정하라', '1동'), ('박소영', '1동'), ('박가영', '1동'),
        ('정소영', '2동'), ('홍현의', '2동'), ('문선희', '2동'), ('김민정', '2동'),
        ('김한솔', '2동'), ('이선아', '2동')
    ]
    conn = sqlite3.connect('prime_nurse_system.db')
    c = conn.cursor()
    for name, unit in nurses:
        c.execute("INSERT OR IGNORE INTO nurses (name, unit) VALUES (?, ?)", (name, unit))
    conn.commit()
    conn.close()

# --- 2. 데이터 정제 유틸리티 ---

def safe_expand_dates(date_str, year):
    """'3/30~4/10' 형태의 문자열을 개별 날짜 리스트로 변환"""
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

def extract_plan_data(uploaded_file, year, exclude_names):
    """배정표(Plan) 핀셋 추출: 불필요한 구역/명단 제외하고 [병동+이름]만 추출"""
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    plan_list = []
    for sheet_name, df in all_sheets.items():
        shift_idx, date_cols = -1, []
        for i in range(min(10, len(df))):
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
                # 핀셋 패턴: [병동번호] + [공백/엔터] + [이름]
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell_text)
                if match:
                    ward, name = match.group(1), match.group(2)
                    if name in exclude_names: continue
                    date_header = str(df.columns[c_idx])
                    dates = safe_expand_dates(date_header if '~' in date_header else cell_text, year)
                    for d in dates:
                        plan_list.append({'날짜': d.strftime('%Y-%m-%d'), '성함': name, '계획병동': ward, '근무조': curr_shift})
    return pd.DataFrame(plan_list)

def clean_actual_data(uploaded_file, year, month_int, exclude_names):
    """실제 근무표(Actual) 정제: P- 코드 분석 (D4 포함)"""
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    actual_list = []
    for sheet_name, df in all_sheets.items():
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
                        # D4 또는 D는 D로 인식
                        shift = 'D' if any(x in code for x in ['D', 'D4']) else 'E'
                        actual_list.append({
                            '날짜': datetime(year, month_int, int(d_match[0])).strftime('%Y-%m-%d'),
                            '성함': name, '실제병동': str(int(ward_match.group(1))), '근무조': shift
                        })
    return pd.DataFrame(actual_list)

def get_strategic_report(unit):
    """차기 대기 병동 전략 추천"""
    conn = sqlite3.connect('prime_nurse_system.db')
    nurses = pd.read_sql_query(f"SELECT * FROM nurses WHERE unit = '{unit}'", conn)
    # 병동 리스트는 실제 운영에 맞춰 수정 가능
    all_wards = ['41', '51', '61', '71', '72', '85', '91', '101', '111', '116', '122', '131']
    recs = []
    for _, n in nurses.iterrows():
        visited = set(n['visited_wards'].split(',')) if n['visited_wards'] else set()
        not_visited = [w for w in all_wards if w not in visited]
        recommend = not_visited[0] if not_visited else "숙련도 유지"
        recs.append({
            "성함": n['name'], "결원대체 횟수": n['sub_count'],
            "차기 추천 병동": recommend, "상태": "⭐⭐⭐(신규)" if recommend in not_visited else "⭐"
        })
    conn.close()
    return pd.DataFrame(recs)

# --- 3. UI 구성 (들여쓰기 주의!) ---

st.set_page_config(page_title="프라임 매니저", layout="wide")
init_db()

st.title("🏥 프라임 간호사 스마트 배치 시스템")
st.sidebar.header("🔍 분석 단계 선택")

if st.sidebar.button("⚙️ 간호사 13명 명단 초기 등록"):
    register_initial_nurses()
    st.sidebar.success("등록 완료!")

step = st.sidebar.radio("작업 선택", ["1. 배정표(Plan) 검증", "2. 근무표(Actual) 검증", "3. 통합 분석 및 전략 추천"])
selected_year = st.sidebar.selectbox("연도 설정", [2026, 2027])
exclude_names = ['고정민']

# Step 1: 배정표 검증
if step == "1. 배정표(Plan) 검증":
    st.header("📋 대기배정표(Plan) 핀셋 추출")
    up_p = st.file_uploader("배정표 엑셀 업로드", type="xlsx")
    if up_p:
        with st.spinner('데이터를 추출 중입니다...'):
            df_plan = extract_plan_data(up_p, selected_year, exclude_names)
        if not df_plan.empty:
            st.success(f"✅ {len(df_plan)}개의 일별 데이터를 추출했습니다.")
            st.dataframe(df_plan, use_container_width=True)
        else:
            st.warning("데이터를 찾지 못했습니다. [병동번호+이름] 형식을 확인하세요.")

# Step 2: 근무표 검증
elif step == "2. 근무표(Actual) 검증":
    st.header("📅 실제 근무표(Actual) 정제")
    up_a = st.file_uploader("근무표 엑셀 업로드", type="xlsx")
    sel_month = st.sidebar.selectbox("해당 월 선택", [f"{i}월" for i in range(1, 13)])
    month_int = int(re.findall(r'\d+', sel_month)[0])
    if up_a:
        df_actual = clean_actual_data(up_a, selected_year, month_int, exclude_names)
        if not df_actual.empty:
            st.success(f"✅ {len(df_actual)}개의 근무 데이터를 정제했습니다.")
            st.dataframe(df_actual, use_container_width=True)
        else:
            st.warning("P- 코드를 찾지 못했습니다.")

# Step 3: 통합 비교 및 전략 추천
elif step == "3. 통합 분석 및 전략 추천":
    st.header("⚖️ 계획 vs 실제 통합 분석 및 미래 전략")
    c1, c2 = st.columns(2)
    with c1: up_p = st.file_uploader("1. 배정표(Plan) 업로드", type="xlsx", key="p3")
    with c2: up_a = st.file_uploader("2. 근무표(Actual) 업로드", type="xlsx", key="a3")
    sel_month = st.sidebar.selectbox("해당 월 선택", [f"{i}월" for i in range(1, 13)], key="m3")
    month_int = int(re.findall(r'\d+', sel_month)[0])

    if up_p and up_a:
        df_p = extract_plan_data(up_p, selected_year, exclude_names)
        df_a = clean_actual_data(up_a, selected_year, month_int, exclude_names)
        
        if not df_p.empty and not df_a.empty:
            merged = pd.merge(df_a, df_p, on=['날짜', '성함'], how='left', suffixes=('', '_계획'))
            merged['상태'] = merged.apply(lambda r: "지원(순환)" if r['실제병동'] == r['계획병동'] else ("결원대체" if pd.notna(r['계획병동']) else "기타"), axis=1)
            
            st.subheader("📊 이번 달 운영 결과 요약")
            summary = merged.groupby(['성함', '상태']).size().unstack(fill_value=0)
            st.table(summary)
            
            st.markdown("---")
            st.header("🚀 다음 달 대기 병동 최적화 전략")
            t1, t2 = st.tabs(["1동 추천 전략", "2동 추천 전략"])
            with t1: st.table(get_strategic_report("1동"))
            with t2: st.table(get_strategic_report("2동"))
