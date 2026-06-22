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
    """배정표(Plan) 데이터를 평일 단위로 분리"""
    expanded_list = []
    df.columns = df.columns.str.strip()
    required = ['시작일', '종료일', '근무조', '배정병동']
    if not all(any(req in c for c in df.columns) for req in required): return pd.DataFrame()
    
    c_start = next(c for c in df.columns if '시작일' in c)
    c_end = next(c for c in df.columns if '종료일' in c)
    c_shift = next(c for c in df.columns if '근무조' in c)
    c_ward = next(c for c in df.columns if '병동' in c)
    c_name = next((c for c in df.columns if '성함' in c), None)

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
                        '계획병동': str(row[c_ward]).strip()
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

def get_refined_ward_data(uploaded_file, year, month_int):
    """실제 근무표(Actual) 파싱"""
    if uploaded_file.name.endswith('.csv'): df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    else: df = pd.read_excel(uploaded_file)
    
    df.columns = df.columns.str.strip()
    name_col = next((c for c in df.columns if '명' in str(c)), None)
    if not name_col: return pd.DataFrame()
        
    day_cols = [c for c in df.columns if '일' in str(c)]
    processed_data = []
    
    for d_col in day_cols:
        day_match = re.findall(r'\d+', str(d_col))
        if not day_match: continue
        day = int(day_match[0])
        
        for _, row in df.iterrows():
            name = str(row[name_col]).strip()
            if name in ['nan', 'None', '', '명', '성', '월', '성명', '이름']: continue
            
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

def get_replacement_system_data(uploaded_file):
    """[3단 크로스체크] 결원대체 시스템 내역 파싱 (날짜, 이름, 병동 숫자 추출)"""
    if uploaded_file.name.endswith('.csv'): df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    else: df = pd.read_excel(uploaded_file)
        
    df.columns = df.columns.str.strip()
    
    # 사내 시스템 컬럼명 탐색
    c_date = next((c for c in df.columns if '발생일' in c or '날짜' in c), None)
    c_name = next((c for c in df.columns if '대체' in c and '성명' in c), None)
    c_ward = next((c for c in df.columns if '병동' in c), None)
    
    rep_list = []
    if c_date and c_name and c_ward:
        for _, row in df.iterrows():
            try:
                dt_str = str(row[c_date]).split()[0]
                dt_val = pd.to_datetime(dt_str)
                name_val = str(row[c_name]).strip()
                ward_val = str(row[c_ward]).strip()
                
                # 병동명에서 숫자만 깔끔하게 추출 (예: '105병동' -> '105')
                ward_nums = re.findall(r'\d+', ward_val)
                
                if name_val and name_val not in ['nan', 'None', ''] and ward_nums:
                    rep_list.append({
                        '날짜': dt_val,
                        '성함': name_val,
                        '결원신청병동': str(int(ward_nums[0]))
                    })
            except: continue
    return pd.DataFrame(rep_list).drop_duplicates()

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
st.title("🏥 데이터 기반 인재 육성 & 실시간 모니터링 시스템")

if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

# 설정
st.sidebar.header("🛠️ 정제 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("기준 월", [f"{i}월" for i in range(1, 13)], index=3)
month_int = int(re.findall(r'\d+', selected_month)[0])

tab1, tab2, tab3, tab4 = st.tabs(["📂 1단계: 업로드", "🔍 2단계: 교차검증", "📊 3단계: 모니터링", "🎯 4단계: 배정 추천"])

with tab1:
    st.info("💡 4가지 파일을 모두 업로드하여 교차 검증을 실행하세요.")
    col1, col2, col3, col4 = st.columns(4)
    file_p = col1.file_uploader("1. 과거 배정표 (Plan)", type=["xlsx", "csv"])
    file_a = col2.file_uploader("2. 과거 실제 근무표 (Actual)", type=["xlsx", "csv"])
    file_rep = col3.file_uploader("3. 대체간호사 시스템 내역", type=["xlsx", "csv"])
    file_r = col4.file_uploader("4. 차월 지원 요청 (Request)", type=["xlsx", "csv"])

with tab2:
    if file_p and file_a and file_rep and file_r:
        if st.button("🚀 3단 교차검증 및 데이터 정제 시작"):
            def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
            
            # 1. 파일 파싱
            df_p = expand_generic_data(load_df(file_p))
            df_a = get_refined_ward_data(file_a, selected_year, month_int)
            df_rep = get_replacement_system_data(file_rep)
            
            # 2. 데이터 병합 (날짜 + 이름 기준)
            df_master = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
            if not df_rep.empty:
                df_master = pd.merge(df_master, df_rep, on=['날짜', '성함'], how='left')
            else:
                df_master['결원신청병동'] = None
                
            # 3. 🚨 [핵심] 역할 및 현장 긴급 스위치 감지 로직
            def determine_role(row):
                if pd.isna(row['실제병동']): return None
                if pd.isna(row['결원신청병동']): return '지원'
                if str(row['실제병동']) == str(row['결원신청병동']): return '결원'
                return '⚠️긴급변경'
                
            df_master['실제역할'] = df_master.apply(determine_role, axis=1)
            
            st.session_state.df_master = df_master
            st.session_state.df_req_next = expand_generic_data(load_df(file_r))
            st.success("✅ 3단 교차 검증(날짜+이름+병동) 완벽 완료! 3단계 모니터링 탭을 확인하세요.")
    else: st.warning("파일 4개를 모두 업로드해 주세요.")

with tab3:
    if not st.session_state.df_master.empty:
        df_all = st.session_state.df_master.copy()
        df_all['월'] = df_all['날짜'].dt.month
        
        selected_m = st.selectbox("분석할 월 선택", sorted(df_all['월'].unique()), format_func=lambda x: f"{x}월")
        df = df_all[df_all['월'] == selected_m].copy()
        all_nurses = sorted(df_all['성함'].unique())
        all_days = range(1, 32)
        
        s1, s2 = st.tabs(["📊 1. 병동별 누적 경험치 집계", "🚨 2. 매칭 추적 및 긴급변경 모니터링"])
        
        with s1:
            st.subheader("💡 간호사별 육성 현황 (병동별 업무 난이도 매칭)")
            selected_nurse_view = st.selectbox("조회할 간호사 선택", all_nurses)
            nurse_df = df[df['성함'] == selected_nurse_view]
            
            sup_counts = nurse_df[nurse_df['실제역할'] == '지원'].groupby('실제병동').size().reset_index(name='지원 횟수(워밍업)')
            sup_counts.rename(columns={'실제병동': '병동'}, inplace=True)
            
            # 결원과 긴급변경 모두 '결원대체(실전)'로 카운트하여 경험치 반영
            rep_counts = nurse_df[nurse_df['실제역할'].isin(['결원', '⚠️긴급변경'])].groupby('실제병동').size().reset_index(name='결원대체 횟수(독립수행)')
            rep_counts.rename(columns={'실제병동': '병동'}, inplace=True)
            
            summary_res = pd.merge(sup_counts, rep_counts, on='병동', how='outer').fillna(0)
            if not summary_res.empty:
                summary_res['지원 횟수(워밍업)'] = summary_res['지원 횟수(워밍업)'].astype(int)
                summary_res['결원대체 횟수(독립수행)'] = summary_res['결원대체 횟수(독립수행)'].astype(int)
            
            st.dataframe(summary_res, use_container_width=True)

        with s2:
            st.subheader("🔍 일별 매칭 추적표 (형식: 계획병동 ➔ 실제출근병동(역할))")
            st.error("💡 '⚠️긴급변경' 표시는 사내 서류상 결원 신청 병동과 실제 현장 출근 병동이 다름을 의미합니다.")
            
            def tracking_flow(row):
                p = str(row['계획병동']).strip() if pd.notna(row['계획병동']) else "-"
                a = str(row['실제병동']).strip() if pd.notna(row['실제병동']) else "-"
                role = str(row['실제역할'])
                
                if p == "-" and a == "-": return ""
                if role == '지원': return f"{p} ➔ {a}(지원)"
                elif role == '결원': return f"{p} ➔ {a}(결원)"
                elif role == '⚠️긴급변경': return f"{p} ➔ {a}(⚠️긴급변경)"
                else: return f"{p} ➔ {a}"
                
            df['매칭흐름'] = df.apply(tracking_flow, axis=1)
            
            pivot_compare = df.pivot_table(
                index='성함', columns=df['날짜'].dt.day, values='매칭흐름', aggfunc='first'
            ).reindex(index=all_nurses, columns=all_days).fillna("")
            
            st.dataframe(pivot_compare, use_container_width=True)
            
    else: st.info("2단계 정제를 실행하세요.")

with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_master = st.session_state.df_master
        df_req = st.session_state.df_req_next
        st.header("🎯 차월 맞춤형(성장 기반) 배정 추천")
        weeks = sorted(df_req['주차'].unique())
        selected_week = st.selectbox("배정 주차 선택", weeks)
        week_info = df_req[df_req['주차'] == selected_week]
        selected_nurse = st.selectbox("배정할 간호사 선택", sorted(list(NURSE_TO_BLD.keys())))
        
        col_logic, col_select = st.columns(2)
        with col_logic:
            st.subheader("⚙️ 근무조 패턴 분석")
            hist_list = get_recent_history_list(df_master, selected_nurse, week_info['날짜'].min())
            rec_shift = recommend_shift_logic(hist_list)
            st.info(f"💡 피로도 방지 로직 추천 근무: **{rec_shift}**")
        with col_select:
            final_shift = st.radio("배정 근무 선택", ["D", "E"], index=0 if rec_shift == "D" else 1, horizontal=True)

        st.divider()
        st.subheader(f"🏥 {selected_nurse} 역량 기반 병동 매칭")
        allow_switch = st.checkbox("🚩 타 동(Building) 스위치 허용")
        
        avail_today = df_req[(df_req['주차'] == selected_week) & (df_req['계획근무조'] == final_shift)]
        if not avail_today.empty:
            my_bld = NURSE_TO_BLD.get(selected_nurse, "1동")
            
            nurse_history = df_master[df_master['성함'] == selected_nurse]
            sup_dict = nurse_history[nurse_history['실제역할'] == '지원'].groupby('실제병동').size().to_dict()
            # 결원과 긴급변경 모두 결원대체 경험치로 포함
            rep_dict = nurse_history[nurse_history['실제역할'].isin(['결원', '⚠️긴급변경'])].groupby('실제병동').size().to_dict()
            
            recommend_list = []
            for w in avail_today['계획병동'].unique():
                if not allow_switch and WARD_TO_BLD.get(w) != my_bld: continue
                c_sup = sup_dict.get(w, 0)
                c_rep = rep_dict.get(w, 0)
                
                priority = "3순위 (인큐베이팅 요망)"
                if c_sup > 0 and c_rep == 0: priority = "1순위 (안전 최우선/워밍업 완료)"
                elif c_sup > 0 and c_rep > 0: priority = "2순위 (경험치 균형 체크)"
                
                recommend_list.append({
                    "병동": w, "소속": WARD_TO_BLD.get(w, "기타"), 
                    "지원(경험) 횟수": c_sup, "결원대체(고난도) 횟수": c_rep,
                    "배정 알고리즘 추천도": priority
                })
                
            if recommend_list:
                res_df = pd.DataFrame(recommend_list).sort_values(by=["결원대체(고난도) 횟수", "배정 알고리즘 추천도"])
                st.dataframe(res_df, use_container_width=True)
            else: st.warning("조건에 맞는 병동이 없습니다.")
        else: st.error("해당 주차 근무조 요청이 없습니다.")
    else: st.info("1, 2단계를 완료해 주세요.")
