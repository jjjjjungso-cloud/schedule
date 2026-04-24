import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta

# --- 1. 데이터베이스 초기화 및 초기 설정 ---
def init_db():
    conn = sqlite3.connect('prime_nurse_system.db')
    c = conn.cursor()
    # 간호사 마스터: unit(1동/2동), sub_count(누격 결원대체), visited_wards(방문이력)
    c.execute('''CREATE TABLE IF NOT EXISTS nurses (
                    name TEXT PRIMARY KEY, unit TEXT, sub_count INTEGER DEFAULT 0,
                    last_d_dedicated TEXT, visited_wards TEXT)''')
    # 실적 로그: [이름 + 날짜] 유니크 설정으로 중복 방지
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
        c.execute("INSERT OR IGNORE INTO nurses (name, unit, sub_count, visited_wards) VALUES (?, ?, 0, '')", (name, unit))
    conn.commit()
    conn.close()

# --- 2. 데이터 정제 엔진 (핀셋 추출 로직) ---

def safe_expand_dates(date_str, year):
    """'3/30~4/10' 형태를 개별 날짜로 확장"""
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
    """배정표에서 '병동번호+이름' 패턴만 핀셋 추출 (근무구역 등 무시)"""
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    plan_list = []
    for _, df in all_sheets.items():
        shift_idx, date_cols = -1, []
        # 열 위치 자동 탐색 (상단 10줄 스캔)
        for i in range(min(10, len(df))):
            row_vals = df.iloc[i].astype(str).tolist()
            for j, val in enumerate(row_vals):
                if '근무조' in val: shift_idx = j
                if '~' in val and j not in date_cols: date_cols.append(j)
        if shift_idx == -1: shift_idx = 1
        
        curr_shift = "D"
        for idx, row in df.iterrows():
            s_val = str(row.iloc[shift_idx]).upper()
            if 'D' in s_val: curr_shift = "D"
            elif 'E' in s_val: curr_shift = "E"
            
            for c_idx in date_cols:
                cell_text = str(row.iloc[c_idx])
                # 패턴: [병동번호] + [이름] (예: "72\n박소영")
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
    """근무표 정제: P- 코드 분석 (D4는 D로 인정)"""
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
                        # D4 포함 여부 확인하여 근무조 결정
                        shift = 'D' if any(x in code for x in ['D', 'D4']) else 'E'
                        actual_list.append({
                            '날짜': datetime(year, month_int, int(d_match[0])).strftime('%Y-%m-%d'),
                            '성함': name, '실제병동': str(int(ward_match.group(1))), '근무조': shift
                        })
    return pd.DataFrame(actual_list)

# --- 3. 전략 알고리즘 (순번제 및 추천) ---

def get_strategic_report(unit):
    """동별 독립 순번제 및 차기 병동 추천"""
    conn = sqlite3.connect('prime_nurse_system.db')
    nurses = pd.read_sql_query(f"SELECT * FROM nurses WHERE unit = '{unit}'", conn)
    all_wards = ['41', '51', '61', '71', '72', '85', '91', '101', '111', '116', '122', '131']
    recs = []
    for _, n in nurses.iterrows():
        visited = set(n['visited_wards'].split(',')) if n['visited_wards'] else set()
        not_visited = [w for w in all_wards if w not in visited]
        recommend = not_visited[0] if not_visited else "숙련도 유지"
        recs.append({
            "성함": n['name'], "결원대체(누적)": f"{n['sub_count']}회",
            "D전담 이력": n['last_d_dedicated'] if n['last_d_dedicated'] else "이력없음",
            "차기 추천 병동": recommend, "우선순위": "⭐⭐⭐" if recommend in not_visited else "⭐"
        })
    conn.close()
    return pd.DataFrame(recs)

# --- 4. 메인 UI 구성 ---

st.set_page_config(page_title="프라임 스마트 시스템", layout="wide")
init_db()

st.title("🏥 프라임 간호사 스마트 배치 및 전략 관리")
st.sidebar.header("🔍 분석 설정")

if st.sidebar.button("⚙️ 간호사 13명 초기 등록 (1회 클릭)"):
    register_initial_nurses()
    st.sidebar.success("등록 완료!")

selected_step = st.sidebar.radio("작업 단계", ["1. 데이터 개별 검증", "2. 통합 분석 및 결과 저장", "3. 다음 달 배정 전략"])
year = st.sidebar.selectbox("연도 설정", [2026, 2027])
exclude_names = ['고정민']

# Step 1: 개별 검증
if selected_step == "1. 데이터 개별 검증":
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 배정표(Plan) 정제 결과")
        up_p = st.file_uploader("배정표 업로드", type="xlsx", key="up_p1")
        if up_p:
            df_p = clean_plan_data(up_p, year, exclude_names)
            st.dataframe(df_p, use_container_width=True)
    with col2:
        st.subheader("📅 근무표(Actual) 정제 결과")
        up_a = st.file_uploader("근무표 업로드", type="xlsx", key="up_a1")
        month_sel = st.selectbox("해당 월", [f"{i}월" for i in range(1, 13)], key="m1")
        if up_a:
            df_a = clean_actual_data(up_a, year, int(month_sel[:-1]), exclude_names)
            st.dataframe(df_a, use_container_width=True)

# Step 2: 통합 분석
elif selected_step == "2. 통합 분석 및 결과 저장":
    st.header("⚖️ 계획 vs 실제 통합 분석 리포트")
    c1, c2 = st.columns(2)
    with c1: up_p = st.file_uploader("배정표 업로드", type="xlsx", key="up_p2")
    with c2: up_a = st.file_uploader("근무표 업로드", type="xlsx", key="up_a2")
    month_sel = st.sidebar.selectbox("분석 월", [f"{i}월" for i in range(1, 13)], key="m2")
    
    if up_p and up_a:
        df_p = clean_plan_data(up_p, year, exclude_names)
        df_a = clean_actual_data(up_a, year, int(month_sel[:-1]), exclude_names)
        
        if not df_p.empty and not df_a.empty:
            # 계획병동과 실제병동 매칭
            merged = pd.merge(df_a, df_p, on=['날짜', '성함'], how='left', suffixes=('', '_계획'))
            
            def check_status(row):
                if pd.isna(row['계획병동']): return "기타(로그없음)"
                return "지원(순환)" if row['실제병동'] == row['계획병동'] else "결원대체"
            
            merged['상태'] = merged.apply(check_status, axis=1)
            
            st.subheader(f"📊 {month_sel} 운영 실적 요약")
            summary = merged.groupby(['성함', '상태']).size().unstack(fill_value=0)
            st.table(summary)
            
            with st.expander("🔍 상세 대조 내역 보기"):
                st.dataframe(merged[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']], use_container_width=True)
            
            if st.button("📥 분석 결과를 데이터베이스에 저장"):
                st.balloons()
                st.success("이번 달 실적이 이력에 반영되었습니다.")
        else:
            st.warning("데이터 정제 결과가 비어있습니다. 1단계를 먼저 확인하세요.")

# Step 3: 차기 전략
elif selected_step == "3. 다음 달 배정 전략":
    st.header("🚀 다음 달 대기 병동 최적화 제안")
    st.write("분석된 병동 경험 데이터를 바탕으로 숙련도를 평준화할 수 있는 배정을 추천합니다.")
    t1, t2 = st.tabs(["1동 전략 가이드", "2동 전략 가이드"])
    with t1: st.table(get_strategic_report("1동"))
    with t2: st.table(get_strategic_report("2동"))
