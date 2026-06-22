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

tab1, tab2, tab3, tab4 = st.tabs(["📂 1단계: 업로드", "🔍 2단계: 교차검증", "📊 3단계: 모니터링", "🎯 4단계: 결원 발생 시 최적 인력 추천"])

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
            df_p = expand_generic_data(load_df(file_p))
            df_a = get_refined_ward_data(file_a, selected_year, month_int)
            df_rep = get_replacement_system_data(file_rep)
            
            df_master = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
            if not df_rep.empty:
                df_master = pd.merge(df_master, df_rep, on=['날짜', '성함'], how='left')
            else: df_master['결원신청병동'] = None
                
            def determine_role(row):
                if pd.isna(row['실제병동']): return None
                if pd.isna(row['결원신청병동']): return '지원'
                if str(row['실제병동']) == str(row['결원신청병동']): return '결원'
                return '⚠️긴급변경'
                
            df_master['실제역할'] = df_master.apply(determine_role, axis=1)
            st.session_state.df_master = df_master
            st.session_state.df_req_next = expand_generic_data(load_df(file_r))
            st.success("✅ 3단 교차 검증 완벽 완료! 4단계 배정 탭으로 이동하세요.")
    else: st.warning("파일 4개를 모두 업로드해 주세요.")

with tab3:
    if not st.session_state.df_master.empty:
        # (기존 모니터링 탭 로직 동일 - 생략 최소화 유지)
        st.info("이곳은 개인별 모니터링 화면입니다. 4단계 탭에서 실시간 추천을 확인하세요.")

with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_master = st.session_state.df_master
        df_req = st.session_state.df_req_next
        
        st.header("🚨 긴급 결원 발생 시 최적 인력 추천 (3단계 알고리즘)")
        st.markdown("""
        **[추천 알고리즘 로직]**
        * **1순위 (안전 우선):** 해당 병동 '지원(보조)' 유경험자 ➔ 즉시 '결원대체' 투입
        * **2순위 (업무 균형):** 1순위자 중 최근 전체 결원대체 투입 누적 횟수가 적은 간호사 우선
        * **3순위 (인큐베이팅):** 해당 병동 경험이 전혀 없는 간호사 ➔ 결원이 아닌 **'지원(워밍업)'**으로 선제적 투입 권장
        """)
        st.divider()
        
        c1, c2, c3 = st.columns(3)
        weeks = sorted(df_req['주차'].unique())
        req_dates = sorted(df_req['날짜'].dt.date.unique())
        
        # 관리자 입력 조건
        target_date = c1.selectbox("결원 발생 날짜", req_dates)
        target_shift = c2.selectbox("필요 근무조", ["D", "E"])
        target_ward = c3.selectbox("결원 발생 병동", sorted(ALL_WARDS))
        
        if st.button("🔍 최적 인력 추천 알고리즘 가동", type="primary"):
            # 1. 해당 날짜, 근무조에 출근 가능한 간호사 풀(Pool) 추출
            avail_pool = df_req[(df_req['날짜'].dt.date == target_date) & (df_req['계획근무조'] == target_shift)]['성함'].tolist()
            
            if not avail_pool:
                st.error("해당 날짜 및 근무조에 가용한 간호사가 없습니다.")
            else:
                recommend_list = []
                for nurse in avail_pool:
                    nurse_hist = df_master[df_master['성함'] == nurse]
                    
                    # 1. 해당 병동 '지원' 횟수 (안전 우선 지표)
                    sup_target = nurse_hist[(nurse_hist['실제병동'] == target_ward) & (nurse_hist['실제역할'] == '지원')].shape[0]
                    
                    # 2. 전체 병동 대상 '결원/긴급' 누적 투입 횟수 (피로도/균형 지표)
                    rep_total = nurse_hist[nurse_hist['실제역할'].isin(['결원', '⚠️긴급변경'])].shape[0]
                    
                    # 3단계 로직 판별
                    if sup_target > 0:
                        priority_tag = "1~2순위 (안전/균형)"
                        role_tag = "✅ 결원대체 투입"
                        score = 1 # 정렬용
                    else:
                        priority_tag = "3순위 (인큐베이팅)"
                        role_tag = "🌱 지원(워밍업) 선제 파견"
                        score = 2 # 정렬용
                        
                    recommend_list.append({
                        "간호사 성함": nurse,
                        "소속 동": NURSE_TO_BLD.get(nurse, "기타"),
                        f"[{target_ward}병동] 지원 유경험 횟수": sup_target,
                        "최근 총 결원대체 횟수 (피로도)": rep_total,
                        "알고리즘 추천 등급": priority_tag,
                        "시스템 권장 역할": role_tag,
                        "_score": score # 정렬용 숨김 필드
                    })
                
                # 데이터프레임 변환 및 [업무 균형]을 위한 다중 정렬 로직 적용
                df_rec = pd.DataFrame(recommend_list)
                
                # 정렬 규칙: 1순위 그룹 먼저 -> 그 안에서 피로도(총 결원대체) 낮은 사람 먼저 -> 해당 병동 지원 경험 많은 사람 먼저
                df_rec.sort_values(
                    by=['_score', '최근 총 결원대체 횟수 (피로도)', f'[{target_ward}병동] 지원 유경험 횟수'], 
                    ascending=[True, True, False], 
                    inplace=True
                )
                df_rec.drop(columns=['_score'], inplace=True) # 숨김 필드 제거
                df_rec.reset_index(drop=True, inplace=True)
                df_rec.index += 1 # 순위를 1번부터 표시
                
                st.success(f"🏆 {target_ward}병동 결원 발생에 따른 최적 인력 추천 결과입니다.")
                st.dataframe(df_rec, use_container_width=True)
                
                # Top 1 추천 코멘트
                top_1 = df_rec.iloc[0]
                if "1~2순위" in top_1['알고리즘 추천 등급']:
                    st.info(f"💡 **최종 추천:** **{top_1['간호사 성함']} 간호사**를 추천합니다. 해당 병동 경험이 있으며, 최근 결원대체 횟수가 {top_1['최근 총 결원대체 횟수 (피로도)']}회로 팀 내에서 피로도가 비교적 낮아 업무 균형을 유지할 수 있습니다.")
                else:
                    st.warning(f"💡 **최종 추천:** 현재 투입 가능한 간호사 중 {target_ward}병동 경험자가 없습니다! **{top_1['간호사 성함']} 간호사**를 **'지원' 근무로 파견**하여 인큐베이팅(Soft-Landing)을 시작하는 것을 강력히 권장합니다.")
                    
    else: st.info("1단계 업로드 및 2단계 정제를 먼저 완료해 주세요.")
