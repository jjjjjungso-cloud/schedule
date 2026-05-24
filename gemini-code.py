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

# --- [유틸리티 함수] ---

def expand_generic_data(df):
    """시작일~종료일 범위를 평일 단위 행으로 분리"""
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동']
    if not all(any(req in c for c in df.columns) for req in required): return pd.DataFrame()
    
    c_start = next(c for c in df.columns if '시작일' in c)
    c_end = next(c for c in df.columns if '종료일' in c)
    c_shift = next(c for c in df.columns if '근무조' in c)
    c_ward = next(c for c in df.columns if '병동' in c)
    c_name = next((c for c in df.columns if '성함' in c or '이름' in c or '명' in c), None)

    for _, row in df.iterrows():
        try:
            start_dt = pd.to_datetime(row[c_start])
            end_dt = pd.to_datetime(row[c_end])
            curr = start_dt
            while curr <= end_dt:
                if curr.weekday() < 5: 
                    expanded_list.append({
                        '날짜': curr,
                        '주차': f"{curr.isocalendar().week}주차",
                        '성함': str(row[c_name]).strip() if c_name and pd.notna(row[c_name]) else "",
                        '계획근무조': str(row[c_shift]).strip(),
                        '계획병동': str(row[c_ward]).strip(),
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

def clean_actual_data_robust(file_path, year, month_int):
    """[최종] 날짜(열) 기준 스캔으로 데이터 밀림 방지"""
    df = pd.read_csv(file_path, encoding='utf-8-sig')
    name_col = '명' # 고정
    day_cols = [c for c in df.columns if '일' in str(c)]
    
    processed_data = []
    
    for d_col in day_cols:
        day_match = re.findall(r'\d+', str(d_col))
        if not day_match: continue
        day = int(day_match[0])
        
        for _, row in df.iterrows():
            name = str(row[name_col]).strip()
            if name in ['nan', 'None', '', '명', '성', '월', '성명']: continue
            
            val = str(row[d_col]).strip()
            if '/' in val:
                parts = val.split('/')
                if len(parts) > 1:
                    ward_part = parts[1]
                    nums = re.findall(r'\d+', ward_part)
                    if nums:
                        processed_data.append({
                            '날짜': datetime(year, month_int, day),
                            '성함': name,
                            '실제병동': str(int(nums[0]))
                        })
    return pd.DataFrame(processed_data)

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
st.set_page_config(page_title="프라임 배정 최적화 시스템", layout="wide")
st.title("🏥 프라임 데이터 통합 및 배정 최적화 시스템")

if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

# 사이드바 설정
st.sidebar.header("🛠️ 데이터 정제 설정")
selected_year = st.sidebar.selectbox("데이터 생성 연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("데이터 생성 기준 월", [f"{i}월" for i in range(1, 13)], index=3)
month_int = int(re.findall(r'\d+', selected_month)[0])

tab1, tab2, tab3, tab4 = st.tabs(["📂 1단계: 업로드", "🔍 2단계: 정제", "📊 3단계: 분석", "🎯 4단계: 배정"])

with tab1:
    st.info("💡 배정을 위해 3가지 파일을 모두 업로드하세요.")
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan)", type=["xlsx", "csv"])
    file_a = c2.file_uploader("과거 실제 근무표(Actual)", type=["csv"]) # CSV 권장
    file_r = c3.file_uploader("차월 지원 요청 파일(Request)", type=["xlsx", "csv"])

with tab2:
    if file_p and file_a and file_r:
        if st.button("🚀 데이터 통합 정제 시작"):
            def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
            df_p = expand_generic_data(load_df(file_p))
            # 로버스트 파싱 함수 사용
            df_a = clean_actual_data_robust(file_a, selected_year, month_int)
            st.session_state.df_master = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
            st.session_state.df_req_next = expand_generic_data(load_df(file_r))
            st.success("✅ 정제 완료! 3, 4단계로 이동하세요.")
    else: st.warning("파일을 모두 업로드해 주세요.")

with tab3:
    if not st.session_state.df_master.empty:
        df_all = st.session_state.df_master.copy()
        df_all['월'] = df_all['날짜'].dt.month
        selected_m = st.selectbox("분석할 월 선택", sorted(df_all['월'].unique()), format_func=lambda x: f"{x}월")
        df = df_all[df_all['월'] == selected_m].copy()
        all_nurses = sorted(df_all['성함'].unique())
        all_days = range(1, 32)
        
        s1, s2, s3 = st.tabs(["1. 간호사별 지원일수", "2. 월별 배정병동", "3. 월별 실제 근무표"])
        with s1:
            st.dataframe(df.groupby(['성함', '계획병동']).size().unstack(fill_value=0), use_container_width=True)
        with s2:
            pivot_plan = df.pivot_table(index='성함', columns=df['날짜'].dt.day, values='계획병동', aggfunc='first').reindex(index=all_nurses, columns=all_days)
            st.dataframe(pivot_plan, use_container_width=True)
        with s3:
            pivot_actual = df.pivot_table(index='성함', columns=df['날짜'].dt.day, values='실제병동', aggfunc='first').reindex(index=all_nurses, columns=all_days)
            st.dataframe(pivot_actual, use_container_width=True)
    else: st.info("2단계 정제를 실행하세요.")

with tab4:
    # 4단계 배정 로직은 동일
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        # ... (생략: 기존 tab4 코드와 동일하게 유지)
        pass
