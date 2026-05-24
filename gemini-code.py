import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [설정 데이터] ---
WARD_GROUPS = {
    '1동': ['41', '51', '52', '61', '62', '71', '72', '91', '92', '101', '102', '111', '122', '131'],
    '2동': ['66', '75', '76', '85', '86', '96', '105', '106', '116']
}
NURSE_GROUPS = {
    '1동': ['정윤정', '기아현', '김유진', '정하라', '김한솔', '최휘영', '박소영'],
    '2동': ['박가영', '홍현의', '김민정', '정소영', '문선희', '엄현지']
}
NURSE_TO_BLD = {name: bld for bld, names in NURSE_GROUPS.items() for name in names}
WARD_TO_BLD = {ward: bld for bld, wards in WARD_GROUPS.items() for ward in wards}
VALID_WARDS = [str(w) for wards in WARD_GROUPS.values() for w in wards]

# --- [유틸리티 함수] ---

def expand_generic_data(df):
    """계획 데이터(Plan) 정제"""
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동']
    if not all(any(req in c for c in df.columns) for req in required): return pd.DataFrame()
    
    c_start, c_end = next(c for c in df.columns if '시작일' in c), next(c for c in df.columns if '종료일' in c)
    c_shift, c_ward = next(c for c in df.columns if '근무조' in c), next(c for c in df.columns if '병동' in c)
    c_name = next((c for c in df.columns if '성함' in c), None)

    for _, row in df.iterrows():
        try:
            start_dt, end_dt = pd.to_datetime(row[c_start]), pd.to_datetime(row[c_end])
            curr = start_dt
            while curr <= end_dt:
                if curr.weekday() < 5: 
                    expanded_list.append({
                        '날짜': curr,
                        '주차': f"{curr.isocalendar().week}주차",
                        '성함': str(row[c_name]).strip(),
                        '계획근무조': str(row[c_shift]).strip().upper(),
                        '계획병동': str(row[c_ward]).strip(),
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

def clean_actual_data(uploaded_file, year, month_int):
    """[핵심 규칙] 실제 근무표 정제: 슬래시(/) 기준 파싱"""
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        name_cols = [i for i, c in enumerate(df.columns) if '명' in str(c) or '성함' in str(c)]
        if not name_cols: continue
        name_idx = name_cols[0]
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '', 'None']: continue
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                
                code = str(row.iloc[d_idx]).strip().upper()
                
                # 1. '/'가 없거나 빈칸이면 무시
                if '/' not in code or code == '/': continue
                
                # 2. 앞(근무조) / 뒤(병동숫자) 분리
                parts = code.split('/', 1)
                front, back = parts[0], parts[1]
                
                # 3. 근무조 및 병동 추출
                shift = 'E' if 'E' in front else 'D'
                ward_nums = re.findall(r'\d+', back)
                
                if ward_nums and ward_nums[0] in VALID_WARDS:
                    actual_list.append({
                        '날짜': datetime(year, month_int, int(d_match[0])),
                        '성함': name,
                        '실제근무조': shift,
                        '실제병동': ward_nums[0]
                    })
    return pd.DataFrame(actual_list)

def recommend_shift_logic(history_list):
    if not history_list: return "D"
    last_shift = history_list[-1]
    count = 0
    for s in reversed(history_list):
        if s == last_shift: count += 1
        else: break
    return last_shift if count < 2 else ("D" if last_shift == "E" else "E")

def get_recent_history_list(df, nurse_name, target_date):
    if df.empty: return []
    target_dt = pd.to_datetime(target_date)
    start_dt = target_dt - timedelta(weeks=5)
    hist = df[(df['성함'] == nurse_name) & (df['날짜'] >= start_dt) & (df['날짜'] < target_dt)]
    if hist.empty: return []
    return hist.sort_values('날짜').groupby('주차')['계획근무조'].first().tolist()

# --- 메인 UI ---
st.set_page_config(page_title="프라임 분석 시스템", layout="wide")
st.title("🏥 프라임 데이터 통합 및 배정 분석 시스템")

if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("과거 실제근무 기준 월", [f"{i}월" for i in range(1, 13)], index=3)
month_int = int(re.findall(r'\d+', selected_month)[0])

tab1, tab2, tab3, tab4 = st.tabs(["📂 1단계: 업로드 & 정제", "📊 3단계: 분석", "🎯 4단계: 배정", "📋 참고"])

with tab1:
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan)", type=["xlsx", "csv"])
    file_a = c2.file_uploader("과거 실제 근무표(Actual)", type=["xlsx", "csv"])
    file_r = c3.file_uploader("차월 지원 요청 파일(Request)", type=["xlsx", "csv"])
    if st.button("🚀 데이터 통합 정제 시작"):
        df_p = expand_generic_data(pd.read_csv(file_p) if file_p.name.endswith('csv') else pd.read_excel(file_p))
        df_a = clean_actual_data(file_a, selected_year, month_int)
        df_p['날짜'] = pd.to_datetime(df_p['날짜'])
        df_a['날짜'] = pd.to_datetime(df_a['날짜'])
        st.session_state.df_master = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
        st.session_state.df_req_next = expand_generic_data(pd.read_csv(file_r) if file_r.name.endswith('csv') else pd.read_excel(file_r))
        st.success("✅ 정제 완료!")

with tab3:
    if not st.session_state.df_master.empty:
        s1, s2, s3 = st.tabs(["🕵️‍♀️ 간호사별 지원일수", "📅 월별 배정표(Plan)", "📅 월별 실제 근무표(Actual)"])
        df = st.session_state.df_master.copy()
        all_nurses, all_days = sorted(df['성함'].unique()), range(1, 32)
        
        with s1:
            st.subheader("간호사별 누적 병동 지원 횟수")
            st.dataframe(df.groupby(['성함', '계획병동']).size().unstack(fill_value=0), use_container_width=True)
            
        with s2:
            st.subheader("월별 배정표(Plan) - [병동 / 근무조]")
            p_ward = df.pivot_table(index='성함', columns=df['날짜'].dt.day, values='계획병동', aggfunc='first').reindex(index=all_nurses, columns=all_days)
            p_shift = df.pivot_table(index='성함', columns=df['날짜'].dt.day, values='계획근무조', aggfunc='first').reindex(index=all_nurses, columns=all_days)
            st.dataframe(pd.concat([p_ward, p_shift], keys=['병동', '근무조']).sort_index(), use_container_width=True)
            
        with s3:
            st.subheader("월별 실제 근무표(Actual) - [병동 / 근무조]")
            a_ward = df.pivot_table(index='성함', columns=df['날짜'].dt.day, values='실제병동', aggfunc='first').reindex(index=all_nurses, columns=all_days)
            a_shift = df.pivot_table(index='성함', columns=df['날짜'].dt.day, values='실제근무조', aggfunc='first').reindex(index=all_nurses, columns=all_days)
            st.dataframe(pd.concat([a_ward, a_shift], keys=['병동', '근무조']).sort_index(), use_container_width=True)
    else: st.info("1단계에서 정제를 먼저 실행해주세요.")
