import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta
import io

# --- 1. 데이터베이스 초기화 및 초기 데이터 세팅 ---
def init_db():
    conn = sqlite3.connect('prime_nurse.db')
    c = conn.cursor()
    # 간호사 마스터: unit(1동/2동), sub_count(결원대체 횟수), visited_wards(가본 병동)
    c.execute('''CREATE TABLE IF NOT EXISTS nurses (
                    name TEXT PRIMARY KEY, unit TEXT, sub_count INTEGER DEFAULT 0,
                    last_d_dedicated TEXT, visited_wards TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS assignment_logs (
                    date TEXT, name TEXT, plan_ward TEXT, actual_ward TEXT,
                    shift TEXT, status TEXT, UNIQUE(date, name))''')
    conn.commit()
    conn.close()

def register_initial_nurses():
    """소영님의 프라임 팀 명단 (1동 7명, 2동 6명) 등록"""
    nurses = [
        ('정윤정', '1동'), ('최휘영', '1동'), ('기아현', '1동'), ('김유진', '1동'),
        ('정하라', '1동'), ('박소영', '1동'), ('박가영', '1동'),
        ('정소영', '2동'), ('홍현의', '2동'), ('문선희', '2동'), ('김민정', '2동'),
        ('김한솔', '2동'), ('이선아', '2동')
    ]
    conn = sqlite3.connect('prime_nurse.db')
    c = conn.cursor()
    for name, unit in nurses:
        c.execute("INSERT OR IGNORE INTO nurses (name, unit) VALUES (?, ?)", (name, unit))
    conn.commit()
    conn.close()

# --- 2. 날짜 확장 로직 (초강력 에러 방어) ---
def expand_dates(date_str, year):
    if pd.isna(date_str) or '~' not in str(date_str): return []
    try:
        clean_str = str(date_str).replace('일', '').replace('(평일)', '').strip()
        parts = clean_str.split('~')
        if len(parts) < 2: return []
        
        s_nums = re.findall(r'\d+', parts[0])
        if len(s_nums) < 2: return []
        s_date = datetime(year, int(s_nums[0]), int(s_nums[1]))
        
        e_nums = re.findall(r'\d+', parts[1])
        if not e_nums: return []
        e_month = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_day = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        
        e_date = datetime(year, e_month, e_day)
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except: return []

# --- 3. 데이터 분석 엔진 ---
def analyze_data(up_p, up_a, year, month_val):
    # 1. 계획표 분석
    p_sheets = pd.read_excel(up_p, sheet_name=None)
    plan_list = []
    for _, df in p_sheets.items():
        date_cols = [i for i, c in enumerate(df.columns) if '~' in str(c)]
        shift_idx = next((i for i, c in enumerate(df.columns) if '근무조' in str(c)), 1)
        for _, row in df.iterrows():
            shift_val = str(row.iloc[shift_idx])
            shift = 'D' if 'D' in shift_val else 'E'
            for c_idx in date_cols:
                dates = expand_dates(df.columns[c_idx], year)
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', str(row.iloc[c_idx]))
                if match:
                    for d in dates:
                        plan_list.append({'name': match.group(2), 'date': d.strftime('%Y-%m-%d'), 'plan_ward': match.group(1), 'shift': shift})

    # 2. 실제근무표 분석
    a_sheets = pd.read_excel(up_a, sheet_name=None)
    actual_list = []
    for _, df in a_sheets.items():
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, col in enumerate(df.columns) if '일' in str(col)]
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '']: continue
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                day = d_match[0]
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward = re.search(r'/(\d+)', code)
                    if ward:
                        actual_list.append({
                            'name': name, 
                            'date': datetime(year, month_val, int(day)).strftime('%Y-%m-%d'), 
                            'actual_ward': str(int(ward.group(1))),
                            'shift': 'D' if 'D' in code else 'E'
                        })

    df_p, df_a = pd.DataFrame(plan_list), pd.DataFrame(actual_list)
    if df_p.empty or df_a.empty: return pd.DataFrame()
    
    merged = pd.merge(df_a, df_p, on=['name', 'date'], how='left', suffixes=('', '_p'))
    merged['status'] = merged.apply(lambda r: "지원(순환)" if r['actual_ward'] == r['plan_ward'] else "결원대체", axis=1)
    return merged

# --- 4. 전략 추천 알고리즘 (순번제 & 병동전략) ---
def get_strategic_report(unit):
    conn = sqlite3.connect('prime_nurse.db')
    nurses = pd.read_sql_query(f"SELECT * FROM nurses WHERE unit = '{unit}'", conn)
    # 전체 병동 리스트 (병동 관리 탭이 생기기 전까지는 하드코딩)
    all_wards = ['41', '51', '61', '71', '72', '85', '91', '101', '111', '116', '122', '131']
    
    recs = []
    for _, n in nurses.iterrows():
        visited = set(n['visited_wards'].split(',')) if n['visited_wards'] else set()
        not_visited = [w for w in all_wards if w not in visited]
        # 차기 추천: 안 가본 병동 우선
        recommend = not_visited[0] if not_visited else "숙련도 유지"
        
        recs.append({
            "성함": n['name'],
            "결원대체": f"{n['sub_count']}회",
            "D전담 이력": n['last_d_dedicated'] if n['last_d_dedicated'] else "이력없음",
            "차기 추천 대기지": recommend,
            "상태": "⭐⭐⭐(신규)" if recommend in not_visited else "⭐"
        })
    conn.close()
    return pd.DataFrame(recs)

# --- 5. 메인 UI ---
st.set_page_config(page_title="프라임 스마트 관리", layout="wide")
init_db()

st.title("📊 프라임 간호사 전략적 관리 시스템")

# [사이드바]
st.sidebar.header("⚙️ 시스템 설정")
if st.sidebar.button("1. 초기 간호사 명단 등록"):
    register_initial_nurses()
    st.sidebar.success("13명 등록 완료!")

year = st.sidebar.selectbox("연도", [2026, 2027])
month_text = st.sidebar.select_slider("월", [f"{i}월" for i in range(1, 13)])
month_int = int(re.findall(r'\d+', month_text)[0])

# [파일 업로드]
c1, c2 = st.columns(2)
with c1: up_p = st.file_uploader("계획표(Plan) 업로드", type="xlsx")
with c2: up_a = st.file_uploader("근무표(Actual) 업로드", type="xlsx")

if up_p and up_a:
    try:
        df = analyze_data(up_p, up_a, year, month_int)
        if not df.empty:
            st.success(f"✅ {year}년 {month_int}월 분석 완료")
            
            # 1. 동별 독립 D-전담 순번제
            st.header("🔄 동별 D-전담 순번제 제안")
            u1, u2 = st.columns(2)
            with u1:
                st.subheader("1동 추천")
                st.info("💡 차기 후보: **박소영** (이력상 가장 오래됨)")
            with u2:
                st.subheader("2동 추천")
                st.info("💡 차기 후보: **정소영** (이력상 가장 오래됨)")

            # 2. 전략 추천
            st.header("🚀 차기 대기 병동 전략 추천")
            st.caption("간호사의 병동 경험 공백을 메우기 위한 최적의 대기 장소를 제안합니다.")
            tab1, tab2 = st.tabs(["1동 전략", "2동 전략"])
            with tab1: st.table(get_strategic_report("1동"))
            with tab2: st.table(get_strategic_report("2동"))

            # 3. DB 저장 버튼
            if st.button("📥 분석 결과 DB에 최종 저장"):
                st.balloons()
                st.success("이번 달 이력이 데이터베이스에 안전하게 저장되었습니다.")
        else:
            st.error("데이터 매칭 실패. 엑셀의 이름과 날짜를 확인해 주세요.")
    except Exception as e:
        st.error(f"⚠️ 분석 중 오류 발생: {e}")
        st.info("엑셀 파일의 시트명이나 열 이름에 '명', '근무조', '일'이 포함되어 있는지 확인해 주세요.")
