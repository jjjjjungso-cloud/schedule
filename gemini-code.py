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
    """시작일~종료일 범위를 평일 단위 행으로 분리 및 주차 부여"""
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
    """파일 객체를 직접 읽고, 날짜 중심으로 스캔하여 실제 근무 데이터 추출"""
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    else:
        df = pd.read_excel(uploaded_file)
    
    df.columns = df.columns.str.strip()
    name_col = '명'
    
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

st.sidebar.header("🛠️ 정제 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("기준 월", [f"{i}월" for i in range(1, 13)], index=3)
month_int = int(re.findall(r'\d+', selected_month)[0])

tab1, tab2, tab3, tab4 = st.tabs(["📂 1단계: 업로드", "🔍 2단계: 정제", "📊 3단계: 분석", "🎯 4단계: 배정"])

with tab1:
    st.info("💡 파일 3개를 모두 업로드하세요.")
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan)", type=["xlsx", "csv"])
    file_a = c2.file_uploader("과거 실제 근무표(Actual)", type=["xlsx", "csv"])
    file_r = c3.file_uploader("차월 지원 요청 파일(Request)", type=["xlsx", "csv"])

with tab2:
    if file_p and file_a and file_r:
        if st.button("🚀 데이터 통합 정제 시작"):
            def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
            df_p = expand_generic_data(load_df(file_p))
            df_a = get_refined_ward_data(file_a, selected_year, month_int)
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
        
        s1, s2 = st.tabs(["📊 1. 개인별 누적 이력 집계 (지원 vs 결원대체)", "🔄 2. 일별 매칭 흐름 비교 (계획 ➔ 실제)"])
        
        with s1:
            st.subheader("💡 간호사별 병동 누적 이력 현황")
            selected_nurse_view = st.selectbox("조회할 간호사 선택", all_nurses)
            nurse_df = df[df['성함'] == selected_nurse_view]
            
            # 병동별 계획(지원) 및 실제(결원대체) 횟수 계산
            p_counts = nurse_df.groupby('계획병동').size().reset_index(name='지원(계획) 횟수')
            p_counts.rename(columns={'계획병동': '병동'}, inplace=True)
            
            a_counts = nurse_df[nurse_df['실제병동'].notna()].groupby('실제병동').size().reset_index(name='결원대체(실제) 횟수')
            a_counts.rename(columns={'실제병동': '병동'}, inplace=True)
            
            summary_res = pd.merge(p_counts, a_counts, on='병동', how='outer').fillna(0)
            summary_res['지원(계획) 횟수'] = summary_res['지원(계획) 횟수'].astype(int)
            summary_res['결원대체(실제) 횟수'] = summary_res['결원대체(실제) 횟수'].astype(int)
            
            st.dataframe(summary_res, use_container_width=True)

        with s2:
            st.subheader("🔍 일별 매칭 흐름 추적 (형식: 계획병동 ➔ 실제병동)")
            st.info("💡 예: '131 ➔ 76'은 원래 131병동 지원 계획이었으나 실제 76병동으로 결원대체 투입된 내역입니다.")
            
            # 계획 ➔ 실제 흐름 문자열 생성 함수
            def tracking_flow(row):
                p = str(row['계획병동']).strip() if pd.notna(row['계획병동']) else "-"
                a = str(row['실제병동']).strip() if pd.notna(row['실제병동']) else "-"
                if p == "-" and a == "-": return ""
                return f"{p} ➔ {a}"
                
            df['매칭흐름'] = df.apply(tracking_flow, axis=1)
            
            # 피벗 테이블 생성
            pivot_compare = df.pivot_table(
                index='성함', 
                columns=df['날짜'].dt.day, 
                values='매칭흐름', 
                aggfunc='first'
            ).reindex(index=all_nurses, columns=all_days).fillna("")
            
            st.dataframe(pivot_compare, use_container_width=True)
            
    else: st.info("2단계 정제를 실행하세요.")

with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_master = st.session_state.df_master
        df_req = st.session_state.df_req_next
        st.header("🎯 차월 배정 의사결정")
        weeks = sorted(df_req['주차'].unique())
        selected_week = st.selectbox("배정 주차 선택", weeks)
        week_info = df_req[df_req['주차'] == selected_week]
        selected_nurse = st.selectbox("간호사를 선택하세요", sorted(list(NURSE_TO_BLD.keys())))
        
        col_logic, col_select = st.columns(2)
        with col_logic:
            st.subheader("⚙️ 근무조 패턴 분석")
            hist_list = get_recent_history_list(df_master, selected_nurse, week_info['날짜'].min())
            rec_shift = recommend_shift_logic(hist_list)
            st.info(f"💡 패턴 분석 결과: 차주 추천 근무는 **{rec_shift}**입니다.")
        with col_select:
            final_shift = st.radio("배정할 근무조 선택", ["D", "E"], index=0 if rec_shift == "D" else 1, horizontal=True)

        st.divider()
        st.subheader(f"🏥 {selected_nurse} 간호사 최적 병동 추천")
        allow_switch = st.checkbox("🚩 타 동(Building) 스위치 허용")
        
        avail_today = df_req[(df_req['주차'] == selected_week) & (df_req['계획근무조'] == final_shift)]
        if not avail_today.empty:
            my_bld = NURSE_TO_BLD.get(selected_nurse, "1동")
            ward_counts = df_master[df_master['성함'] == selected_nurse].groupby('계획병동').size().to_dict()
            recommend_list = []
            for w in avail_today['계획병동'].unique():
                if not allow_switch and WARD_TO_BLD.get(w) != my_bld: continue
                count = ward_counts.get(w, 0)
                recommend_list.append({"병동": w, "소속": WARD_TO_BLD.get(w, "기타"), "누적 방문일수": count})
            if recommend_list:
                res_df = pd.DataFrame(recommend_list).sort_values(by="누적 방문일수")
                st.dataframe(res_df, use_container_width=True)
                top = res_df.iloc[0]
                st.success(f"🏆 최종 추천: **{top['병동']}병동**")
            else: st.warning(f"{my_bld} 내 지원 요청이 없습니다.")
        else: st.error("해당 주차에 선택한 근무조 요청이 없습니다.")
    else: st.info("1, 2단계를 먼저 완료해 주세요.")
