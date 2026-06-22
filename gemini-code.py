import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [초기 설정 및 데이터] ---
st.set_page_config(page_title="프라임 실시간 배정 시스템", layout="wide")

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
@st.cache_data
def expand_generic_data(df):
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
                        '성함': str(row[c_name]).strip() if c_name and pd.notna(row[c_name]) else "",
                        '계획근무조': str(row[c_shift]).strip(),
                        '계획병동': str(row[c_ward]).strip()
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

@st.cache_data
def get_refined_ward_data(df, year, month_int):
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
                    nums = re.findall(r'\d+', parts[1])
                    if nums:
                        processed_data.append({
                            '날짜': datetime(year, month_int, day),
                            '성함': name,
                            '실제병동': str(int(nums[0]))
                        })
    return pd.DataFrame(processed_data)

@st.cache_data
def get_replacement_system_data(df):
    df.columns = df.columns.str.strip()
    c_date = next((c for c in df.columns if '발생일' in c or '날짜' in c), None)
    c_name = next((c for c in df.columns if '대체' in c and '성명' in c), None)
    c_ward = next((c for c in df.columns if '병동' in c), None)
    
    rep_list = []
    if c_date and c_name and c_ward:
        for _, row in df.iterrows():
            try:
                dt_str = str(row[c_date]).split()[0]
                name_val = str(row[c_name]).strip()
                ward_nums = re.findall(r'\d+', str(row[c_ward]).strip())
                if name_val and name_val not in ['nan', 'None', ''] and ward_nums:
                    rep_list.append({
                        '날짜': pd.to_datetime(dt_str),
                        '성함': name_val,
                        '결원신청병동': str(int(ward_nums[0]))
                    })
            except: continue
    return pd.DataFrame(rep_list).drop_duplicates()

# --- [UI: 사이드바] ---
st.sidebar.header("🔄 EMR 데이터 동기화")
st.sidebar.info("정식 전산 반영 전, 엑셀 파일로 EMR DB 연결을 시뮬레이션합니다.")

selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("월", [f"{i}월" for i in range(1, 13)], index=3)
month_int = int(re.findall(r'\d+', selected_month)[0])

file_p = st.sidebar.file_uploader("1. 근무 스케줄 (Plan)", type=["xlsx", "csv"])
file_a = st.sidebar.file_uploader("2. 실제 출근 기록 (Actual)", type=["xlsx", "csv"])
file_rep = st.sidebar.file_uploader("3. 대체간호사 시스템 (System)", type=["xlsx", "csv"])
file_r = st.sidebar.file_uploader("4. 가용 인력 풀 (Request)", type=["xlsx", "csv"])

if st.sidebar.button("🚀 EMR 데이터 동기화 (Sync)"):
    if file_p and file_a and file_rep and file_r:
        def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
        
        df_p = expand_generic_data(load_df(file_p))
        df_a = get_refined_ward_data(load_df(file_a), selected_year, month_int)
        df_rep = get_replacement_system_data(load_df(file_rep))
        
        df_master = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
        if not df_rep.empty:
            df_master = pd.merge(df_master, df_rep, on=['날짜', '성함'], how='left')
        else: df_master['결원신청병동'] = None
            
        def determine_role(row):
            if pd.isna(row['실제병동']): return None
            if pd.isna(row['결원신청병동']): return '지원'
            if str(row['실제병동']) == str(row['결원신청병동']): return '결원대체'
            return '⚠️긴급변경(결원)'
            
        df_master['실제역할'] = df_master.apply(determine_role, axis=1)
        st.session_state.df_master = df_master
        st.session_state.df_req = expand_generic_data(load_df(file_r))
        st.sidebar.success("✅ DB 동기화 완료!")
    else:
        st.sidebar.warning("모든 데이터를 연동해주세요.")

# --- [메인 화면] ---
st.title("🏥 프라임 간호실 실시간 통제 센터 (Live Control Tower)")

if 'df_master' in st.session_state and not st.session_state.df_master.empty:
    df_master = st.session_state.df_master
    df_req = st.session_state.df_req
    
    avail_dates = sorted(df_master['날짜'].dt.date.dropna().unique())
    col_date, _, _ = st.columns(3)
    today_date = col_date.selectbox("📅 현재 시점(Today) 설정", avail_dates, index=len(avail_dates)-1)
    
    df_realtime = df_master[df_master['날짜'].dt.date <= today_date].copy()
    
    tab1, tab2 = st.tabs(["📊 팀 전체 실시간 누적 스탯", "🚨 긴급 결원 배정 마스터 랭킹"])
    
    with tab1:
        st.subheader(f"💡 {today_date} 기준 팀 전체 실시간 이력 보드")
        all_nurses = sorted(df_master['성함'].dropna().unique())
        stat_list = []
        for nurse in all_nurses:
            n_df = df_realtime[df_realtime['성함'] == nurse]
            sup_total = n_df[n_df['실제역할'] == '지원'].shape[0]
            rep_total = n_df[n_df['실제역할'].isin(['결원대체', '⚠️긴급변경(결원)'])].shape[0]
            
            top_wards = n_df['실제병동'].dropna().value_counts().head(2).index.tolist()
            top_wards_str = ", ".join(top_wards) if top_wards else "경험없음"
            
            stat_list.append({
                "성함": nurse,
                "소속": NURSE_TO_BLD.get(nurse, "기타"),
                "누적 지원 횟수 (워밍업)": sup_total,
                "누적 결원대체 횟수 (피로도)": rep_total,
                "주요 투입 병동 (Top 2)": top_wards_str
            })
            
        df_stats = pd.DataFrame(stat_list).sort_values(by="누적 결원대체 횟수 (피로도)", ascending=False).reset_index(drop=True)
        st.dataframe(df_stats, use_container_width=True)

    with tab2:
        st.header("🚨 긴급 결원 발생 즉시 배정 (4단계 육성 알고리즘)")
        st.markdown("""
        **[마스터 추천 로직 (근무조 무관, 프라임 전 인력 대상)]**
        * **1순위:** 지원 경험 O / 결원 경험 X ➔ 워밍업 완료! 결원대체로 독립 수행할 최적기 🚀
        * **2순위:** 지원 경험 O / 결원 경험 O ➔ 안정적이고 완벽히 검증된 결원대체 투입 ✅
        * **3순위:** 지원 경험 X / 결원 경험 O ➔ 하드랜딩 경험자 (투입은 가능하나 정석 코스는 아님) ⚠️
        * **4순위:** 해당 병동 경험 전무 ➔ 결원 파견 금지! 반드시 '지원(워밍업)'으로 선제 투입 요망 🌱
        """)
        st.divider()
        
        c1, c2 = st.columns(2)
        target_date = c1.selectbox("결원 발생 일자 (검색 기준일)", sorted(df_req['날짜'].dt.date.unique()))
        target_ward = c2.selectbox("결원 발생 병동", sorted(ALL_WARDS))
        
        if st.button("🔍 프라임 전체 마스터 랭킹 가동", type="primary"):
            # 프라임 간호실 모든 인력 불러오기
            all_prime_nurses = sorted(list(NURSE_TO_BLD.keys()))
            
            recommend_list = []
            for nurse in all_prime_nurses:
                # 결원 발생일 '직전'까지의 이력만 조회하여 실시간 재현
                nurse_hist = df_master[(df_master['성함'] == nurse) & (df_master['날짜'].dt.date < target_date)]
                
                # 해당 병동 지원 및 결원 횟수 카운트
                sup_target = nurse_hist[(nurse_hist['실제병동'] == target_ward) & (nurse_hist['실제역할'] == '지원')].shape[0]
                rep_target = nurse_hist[(nurse_hist['실제병동'] == target_ward) & (nurse_hist['실제역할'].isin(['결원대체', '⚠️긴급변경(결원)']))].shape[0]
                
                # 피로도 참고용 총 결원대체 누적
                rep_total = nurse_hist[nurse_hist['실제역할'].isin(['결원대체', '⚠️긴급변경(결원)'])].shape[0]
                
                # 팀장님의 4단계 우선순위 로직
                if sup_target > 0 and rep_target == 0:
                    priority_tag = "1순위 (지원O / 결원X)"
                    role_tag = "🚀 결원대체 독립수행 최적기"
                    score = 1
                elif sup_target > 0 and rep_target > 0:
                    priority_tag = "2순위 (지원O / 결원O)"
                    role_tag = "✅ 안정적인 결원 투입"
                    score = 2
                elif sup_target == 0 and rep_target > 0:
                    priority_tag = "3순위 (지원X / 결원O)"
                    role_tag = "⚠️ 하드랜딩 경험 (투입 가능)"
                    score = 3
                else:
                    priority_tag = "4순위 (경험 없음)"
                    role_tag = "🌱 결원 금지 / 지원(워밍업) 요망"
                    score = 4
                    
                recommend_list.append({
                    "간호사 성함": nurse,
                    "소속": NURSE_TO_BLD.get(nurse, "기타"),
                    f"[{target_ward}병동] 지원 횟수": sup_target,
                    f"[{target_ward}병동] 결원대체 횟수": rep_target,
                    "총 결원대체 누적 (참고)": rep_total,
                    "알고리즘 추천 등급": priority_tag,
                    "시스템 권장 포지션": role_tag,
                    "_score": score # 정렬용 숨김 필드
                })
            
            df_rec = pd.DataFrame(recommend_list)
            
            # [핵심 정렬 로직] 1. 추천 등급순 -> 2. 지원횟수 적은 순 -> 3. 총 결원대체 피로도 적은 순
            df_rec.sort_values(
                by=['_score', f'[{target_ward}병동] 지원 횟수', '총 결원대체 누적 (참고)'], 
                ascending=[True, True, True], inplace=True
            )
            df_rec.drop(columns=['_score'], inplace=True)
            df_rec.reset_index(drop=True, inplace=True)
            df_rec.index += 1 # 랭킹 번호 부여
            
            st.success(f"🏆 {target_ward}병동 결원에 대한 프라임 간호실 전체 인력 우선순위 마스터 명단입니다.")
            st.dataframe(df_rec, use_container_width=True)
            
            # AI Control Tower 코멘트 자동 생성
            top_1 = df_rec.iloc[0]
            if "1순위" in top_1['알고리즘 추천 등급']:
                st.info(f"💡 **Control Tower 최종 가이드:** **{top_1['간호사 성함']} 간호사**를 {target_ward}병동 결원대체로 투입하는 것이 가장 이상적입니다. 해당 병동에서 '지원'으로 워밍업을 완벽히 마쳤으며, 이제 결원대체로 독립 수행하며 성장할 최고의 타이밍입니다.")
            elif "2순위" in top_1['알고리즘 추천 등급']:
                st.info(f"💡 **Control Tower 최종 가이드:** 1순위 인력이 불가할 경우, 이미 {target_ward}병동 지원 및 결원 경험이 모두 있는 안정적인 **{top_1['간호사 성함']} 간호사**를 우선 투입하여 환자 간호의 질을 확보하십시오.")
            else:
                st.warning(f"💡 **Control Tower 최종 가이드:** 현재 {target_ward}병동에 결원 투입이 적합한 1, 2순위 경험자가 프라임 내에 매우 부족합니다. 장기적 관점에서 **{top_1['간호사 성함']} 간호사**를 선제적으로 **'지원' 파견**하여 향후 결원 대비를 위한 인큐베이팅을 오늘부터 시작하십시오.")
else:
    st.info("⬅️ 좌측 사이드바에서 EMR 데이터를 동기화(업로드)하면 실시간 통제 센터가 가동됩니다.")
