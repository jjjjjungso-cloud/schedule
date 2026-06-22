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
ALL_WARDS = [w for wards in WARD_GROUPS.values() for w in wards]

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
                
                ward_nums = re.findall(r'\d+', ward_val)
                
                if name_val and name_val not in ['nan', 'None', ''] and ward_nums:
                    rep_list.append({
                        '날짜': dt_val,
                        '성함': name_val,
                        '결원신청병동': str(int(ward_nums[0]))
                    })
            except: continue
    return pd.DataFrame(rep_list).drop_duplicates()

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

tab1, tab2, tab3, tab4 = st.tabs(["📂 1단계: 업로드", "🔍 2단계: 교차검증", "📊 3단계: 모니터링", "🎯 4단계: 결원대체 마스터 랭킹"])

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
        
        st.header("🎯 결원 발생 병동 기준 전 간호사 마스터 랭킹")
        st.markdown("""
        **[팀장님 전용 4단계 인큐베이팅 알고리즘]** (※ 근무조 무관, 전체 프라임 간호사 대상)
        * **1순위:** 지원 이력 **있음** / 결원 이력 **없음** ➔ 🚀 워밍업 완료! 결원대체 실전 투입 최적기
        * **2순위:** 지원 이력 **있음** / 결원 이력 **있음** ➔ ✅ 검증된 자원 (안정적 투입 가능)
        * **3순위:** 지원 이력 **없음** / 결원 이력 **있음** ➔ ⚠️ 하드랜딩 경험자 (워밍업 생략됨)
        * **4순위:** 지원 이력 **없음** / 결원 이력 **없음** ➔ 🌱 결원대체 **절대 금지** (지원 파견 선행 요망)
        """)
        st.divider()
        
        c1, c2 = st.columns(2)
        # 차월 요청 파일에 있는 날짜들을 추출 (미래 혹은 기준일)
        req_dates = sorted(df_req['날짜'].dt.date.unique())
        target_date = c1.selectbox("결원 발생 일자 (검색 기준일)", req_dates)
        target_ward = c2.selectbox("결원 발생 병동", sorted(ALL_WARDS))
        
        if st.button("🔍 전 간호사 마스터 랭킹 가동", type="primary"):
            # 프라임 간호실 전체 간호사 명단
            all_prime_nurses = sorted(list(NURSE_TO_BLD.keys()))
            
            recommend_list = []
            for nurse in all_prime_nurses:
                # 검색 기준일 '직전'까지의 과거 이력만 조회하여 실시간 상태 재현
                nurse_hist = df_master[(df_master['성함'] == nurse) & (df_master['날짜'].dt.date < target_date)]
                
                # 해당 병동 '지원' 및 '결원' 횟수 계산
                sup_count = nurse_hist[(nurse_hist['실제병동'] == target_ward) & (nurse_hist['실제역할'] == '지원')].shape[0]
                rep_count = nurse_hist[(nurse_hist['실제병동'] == target_ward) & (nurse_hist['실제역할'].isin(['결원', '⚠️긴급변경']))].shape[0]
                
                # 피로도 참고용 (전체 병동 결원대체 총합)
                total_rep = nurse_hist[nurse_hist['실제역할'].isin(['결원', '⚠️긴급변경'])].shape[0]
                
                # 4단계 알고리즘 판별
                if sup_count > 0 and rep_count == 0:
                    priority_tag = "1순위"
                    desc = "🚀 실전 투입 최적기 (지원만 O)"
                    score = 1
                elif sup_count > 0 and rep_count > 0:
                    priority_tag = "2순위"
                    desc = "✅ 검증된 안정 자원 (둘 다 O)"
                    score = 2
                elif sup_count == 0 and rep_count > 0:
                    priority_tag = "3순위"
                    desc = "⚠️ 하드랜딩 경험자 (결원만 O)"
                    score = 3
                else:
                    priority_tag = "4순위"
                    desc = "🌱 결원 파견 보류 (경험 전무)"
                    score = 4
                    
                recommend_list.append({
                    "간호사 성함": nurse,
                    "소속": NURSE_TO_BLD.get(nurse, "기타"),
                    f"[{target_ward}병동] 지원 횟수": sup_count,
                    f"[{target_ward}병동] 결원대체 횟수": rep_count,
                    "우선순위 그룹": priority_tag,
                    "상태 진단": desc,
                    "팀 전체 피로도 (총 결원 횟수)": total_rep,
                    "_score": score # 보이지 않는 정렬용 키
                })
                
            df_rec = pd.DataFrame(recommend_list)
            
            # 🎯 [핵심 정렬 로직] 
            # 1. 우선순위 등급순(score) 오름차순 
            # 2. 같은 순위일 경우 지원 횟수가 적은 사람 오름차순 (방금 막 워밍업 끝낸 사람)
            # 3. 팀 전체 피로도(총 결원 횟수) 오름차순
            df_rec.sort_values(
                by=['_score', f'[{target_ward}병동] 지원 횟수', '팀 전체 피로도 (총 결원 횟수)'], 
                ascending=[True, True, True], 
                inplace=True
            )
            df_rec.drop(columns=['_score'], inplace=True)
            df_rec.reset_index(drop=True, inplace=True)
            df_rec.index += 1 # 랭킹 번호 부여
            
            st.success(f"🏆 {target_ward}병동 인력 배정을 위한 프라임 간호실 전체 마스터 랭킹입니다.")
            st.dataframe(df_rec, use_container_width=True)
            
            # AI 요약 코멘트
            top_1 = df_rec.iloc[0]
            if "1순위" in top_1['우선순위 그룹']:
                st.info(f"💡 **AI 배정 가이드:** 1순위인 **{top_1['간호사 성함']} 간호사**를 적극 추천합니다. {target_ward}병동에서 지원 근무로 워밍업({top_1[f'[{target_ward}병동] 지원 횟수']}회)을 마쳤으며, 아직 결원대체 실전 경험이 없어 지금이 완벽하게 독립 수행으로 성장시킬 최적의 타이밍입니다.")
            elif "2순위" in top_1['우선순위 그룹']:
                st.info(f"💡 **AI 배정 가이드:** 현재 1순위(지원만 해본 인력)가 없습니다. 안정적인 병동 운영을 위해 이미 해당 병동에 지원 및 결원 경험이 모두 있는 **{top_1['간호사 성함']} 간호사** 배정을 추천합니다.")
            else:
                st.warning(f"💡 **AI 배정 가이드:** 팀 내에 {target_ward}병동 정석 훈련자(1, 2순위)가 없습니다. 결원대체보다는 향후 원활한 운영을 위해 **{top_1['간호사 성함']} 간호사** 등 경험 없는 인력을 **'지원(워밍업)'**으로 파견하여 사전 경험을 쌓게 해주세요.")
                
    else: st.info("1, 2단계를 완료해 주세요.")
