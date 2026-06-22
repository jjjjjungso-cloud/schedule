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

# --- [유틸리티 함수 (EMR 데이터 파싱 시뮬레이션)] ---
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

# --- [UI: 사이드바 (EMR DB 연동 시뮬레이션)] ---
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

# --- [메인 화면: 실시간 대시보드] ---
st.title("🏥 프라임 간호실 실시간 통제 센터 (Live Control Tower)")

if 'df_master' in st.session_state and not st.session_state.df_master.empty:
    df_master = st.session_state.df_master
    df_req = st.session_state.df_req
    
    # 1. 실시간 시뮬레이션을 위한 '오늘 날짜' 선택
    avail_dates = sorted(df_master['날짜'].dt.date.dropna().unique())
    col_date, _, _ = st.columns(3)
    today_date = col_date.selectbox("📅 현재 시점(Today) 설정 (이 날짜까지의 이력만 실시간 계산됨)", avail_dates, index=len(avail_dates)-1)
    
    # '오늘' 이전의 데이터만 필터링 (완벽한 실시간 재현)
    df_realtime = df_master[df_master['날짜'].dt.date <= today_date].copy()
    
    tab1, tab2 = st.tabs(["📊 팀 전체 실시간 누적 스탯", "🚨 긴급 결원 발생 즉시 배정 (추천 알고리즘)"])
    
    with tab1:
        st.subheader(f"💡 {today_date} 기준 팀 전체 실시간 이력 보드")
        st.info("실시간 동기화된 EMR 데이터를 바탕으로 각 간호사의 현재 피로도와 경험치를 모니터링합니다.")
        
        # 팀 전체 누적 스탯 실시간 계산
        all_nurses = sorted(df_master['성함'].dropna().unique())
        stat_list = []
        for nurse in all_nurses:
            n_df = df_realtime[df_realtime['성함'] == nurse]
            sup_total = n_df[n_df['실제역할'] == '지원'].shape[0]
            rep_total = n_df[n_df['실제역할'].isin(['결원대체', '⚠️긴급변경(결원)'])].shape[0]
            
            # 많이 간 병동 Top 2 추출 (간단한 프로필용)
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
        st.header("🚨 긴급 결원 발생 즉시 배정 (3단계 알고리즘)")
        st.markdown("**[실시간 추천 우선순위]** 1순위: 해당 병동 경험자 ➔ 2순위: 전체 결원 횟수 최저 (피로도 관리) ➔ 3순위: 무경험자 지원(워밍업) 선제 투입")
        st.divider()
        
        c1, c2, c3 = st.columns(3)
        target_date = c1.selectbox("결원 발생 일자", sorted(df_req['날짜'].dt.date.unique()))
        target_shift = c2.selectbox("필요 근무조", ["D", "E"])
        target_ward = c3.selectbox("결원 발생 병동", sorted(ALL_WARDS))
        
        if st.button("🔍 실시간 최적 인력 추천 가동", type="primary"):
            avail_pool = df_req[(df_req['날짜'].dt.date == target_date) & (df_req['계획근무조'] == target_shift)]['성함'].tolist()
            
            if not avail_pool:
                st.error("해당 날짜/근무조에 가용 가능한 프라임 인력이 없습니다.")
            else:
                recommend_list = []
                for nurse in avail_pool:
                    # [핵심] 결원 발생일 '직전'까지의 이력만 조회하여 완벽한 실시간 상황 재현
                    nurse_hist = df_master[(df_master['성함'] == nurse) & (df_master['날짜'].dt.date < target_date)]
                    
                    sup_target = nurse_hist[(nurse_hist['실제병동'] == target_ward) & (nurse_hist['실제역할'] == '지원')].shape[0]
                    rep_total = nurse_hist[nurse_hist['실제역할'].isin(['결원대체', '⚠️긴급변경(결원)'])].shape[0]
                    
                    if sup_target > 0:
                        priority_tag = "1~2순위 (안전 및 균형)"
                        role_tag = "✅ 결원대체 투입 적격"
                        score = 1 
                    else:
                        priority_tag = "3순위 (인큐베이팅)"
                        role_tag = "🌱 지원(워밍업) 파견 권장"
                        score = 2 
                        
                    recommend_list.append({
                        "간호사 성함": nurse,
                        "소속": NURSE_TO_BLD.get(nurse, "기타"),
                        f"[{target_ward}병동] 지원 유경험 (안전)": sup_target,
                        "총 결원대체 누적 (피로도)": rep_total,
                        "알고리즘 추천 등급": priority_tag,
                        "시스템 권장 포지션": role_tag,
                        "_score": score
                    })
                
                df_rec = pd.DataFrame(recommend_list)
                df_rec.sort_values(
                    by=['_score', '총 결원대체 누적 (피로도)', f'[{target_ward}병동] 지원 유경험 (안전)'], 
                    ascending=[True, True, False], inplace=True
                )
                df_rec.drop(columns=['_score'], inplace=True)
                df_rec.reset_index(drop=True, inplace=True)
                df_rec.index += 1
                
                st.success(f"🏆 {target_ward}병동 {target_shift}근무 결원에 대한 실시간 최적 인력 추천 결과입니다.")
                st.dataframe(df_rec, use_container_width=True)
                
                top_1 = df_rec.iloc[0]
                if "1~2순위" in top_1['알고리즘 추천 등급']:
                    st.info(f"💡 **Control Tower 최종 지시:** **{top_1['간호사 성함']} 간호사**를 {target_ward}병동 결원대체로 즉시 투입하십시오. 해당 병동 경험이 있으며, 현재까지의 총 결원대체 피로도({top_1['총 결원대체 누적 (피로도)']}회)가 팀 내에서 가장 안정적인 상태입니다.")
                else:
                    st.warning(f"💡 **Control Tower 최종 지시:** 현재 가용 인력 중 {target_ward}병동 경험자가 없습니다. 환자 안전을 위해 아무나 결원대체로 투입하지 마시고, **{top_1['간호사 성함']} 간호사**를 우선 **'지원'**으로 파견하여 적응 훈련(인큐베이팅)을 실시할 것을 권장합니다.")
else:
    st.info("⬅️ 좌측 사이드바에서 EMR 데이터를 동기화(업로드)하면 실시간 통제 센터가 가동됩니다.")
