import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [설정 데이터] 소영님이 직접 관리하는 구역 ---
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

def expand_plan_data(df):
    """배정표 확장: 평일만 추출 및 주차 부여"""
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    if not all(col in df.columns for col in required): return pd.DataFrame()
    for _, row in df.iterrows():
        try:
            start_dt = pd.to_datetime(row['시작일'])
            end_dt = pd.to_datetime(row['종료일'])
            curr = start_dt
            while curr <= end_dt:
                if curr.weekday() < 5: # 월-금 평일만 반영
                    expanded_list.append({
                        '날짜': curr,
                        '주차': f"{curr.isocalendar().week}주차",
                        '성함': str(row['간호사 성함']).strip(),
                        '계획근무조': str(row['근무조']).strip(),
                        '계획병동': str(row['배정병동'])
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

def clean_actual_data(uploaded_file, year, month_int):
    """실제 근무표 정제: P-코드 추출"""
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '', 'None']: continue
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        shift = 'D' if ('D4' in code or 'D' in code) else 'E'
                        try:
                            actual_list.append({
                                '날짜': datetime(year, month_int, int(d_match[0])),
                                '성함': name,
                                '실제근무조': shift,
                                '실제병동': str(int(ward_match.group(1)))
                            })
                        except: continue
    return pd.DataFrame(actual_list)

def get_recent_history(df, nurse_name, target_date):
    """직전 4주 근무 이력 요약 (4단계 근거용)"""
    if df.empty: return "이력 없음"
    target_dt = pd.to_datetime(target_date)
    four_weeks_ago = target_dt - timedelta(weeks=4)
    hist = df[(df['성함'] == nurse_name) & (df['날짜'] >= four_weeks_ago) & (df['날짜'] < target_dt)]
    if hist.empty: return "최근 기록 없음"
    summary = hist.groupby('주차')['계획근무조'].unique().apply(lambda x: ",".join(x)).to_dict()
    return " | ".join([f"{k}:{v}" for k, v in summary.items()])

# --- 메인 UI ---
st.set_page_config(page_title="프라임 배정 최적화 시스템", layout="wide")
st.title("🏥 프라임 데이터 통합 및 배정 최적화 시스템")

# 세션 스테이트 초기화
if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

# 4단계 탭 구성
tab1, tab2, tab3, tab4 = st.tabs([
    "📂 1단계: 파일 업로드", 
    "🔍 2단계: 데이터 정제 및 검증", 
    "📊 3단계: 누적 데이터 및 경험 분석", 
    "🎯 4단계: 차월 배정 의사결정"
])

with tab1:
    st.info("💡 배정 분석을 위해 총 3가지 파일을 업로드해 주세요.")
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan)", type="xlsx")
    file_a = c2.file_uploader("과거 실제 근무표(Actual)", type="xlsx")
    file_r = c3.file_uploader("차월 지원 요청 파일(Request - 빈 양식)", type="xlsx")

with tab2:
    if file_p and file_a and file_r:
        if st.button("🚀 데이터 정제 및 통합 시작"):
            df_p = expand_plan_data(pd.read_excel(file_p))
            df_a = clean_actual_data(file_a, 2026, 3) # 연도/월 설정
            # 계획과 실제 데이터를 병합하여 마스터 데이터 생성
            st.session_state.df_master = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
            st.session_state.df_req_next = expand_plan_data(pd.read_excel(file_r))
            st.success("✅ 데이터 정제 및 통합이 완료되었습니다!")
            
            col_res1, col_res2 = st.columns(2)
            col_res1.subheader("📋 정제된 계획 데이터")
            col_res1.dataframe(df_p, use_container_width=True)
            col_res2.subheader("📋 정제된 실제 근무 데이터")
            col_res2.dataframe(df_a, use_container_width=True)
    else:
        st.warning("먼저 1단계에서 파일을 업로드해 주세요.")

with tab3:
    if not st.session_state.df_master.empty:
        df_m = st.session_state.df_master
        st.header("📊 누적 데이터 및 경험 분석")
        
        st.subheader("📅 주차별 배정 현황 (연속성 확인)")
        weekly_pivot = df_m.pivot_table(index='성함', columns='주차', values='계획병동', aggfunc=lambda x: ", ".join(sorted(set(x))))
        st.dataframe(weekly_pivot, use_container_width=True)
        
        st.divider()
        st.subheader("🕵️‍♀️ 간호사별 병동 지원 일수 (경험 매트릭스)")
        exp_matrix = df_m.groupby(['성함', '계획병동']).size().unstack(fill_value=0)
        st.dataframe(exp_matrix, use_container_width=True)
        st.caption("※ 표 안의 숫자는 해당 병동에 지원 나간 총 일수(Day)입니다.")
    else:
        st.info("2단계에서 데이터 정제 실행 버튼을 눌러주세요.")

with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_master = st.session_state.df_master
        st.header("🎯 데이터 기반 차월 배정 의사결정")

        # --- 1. 4:3 슬롯 매니저 ---
        st.subheader("1️⃣ 근무조 슬롯 밸런서 (4:3 비율 조정)")
        nurses_1dong = NURSE_GROUPS['1동']
        balancing_data = []
        for name in nurses_1dong:
            hist_str = get_recent_history(df_master, name, "2026-05-01") # 기준일자
            is_must_d = "D" not in hist_str.split('|')[-1] if hist_str != "이력 없음" else False
            balancing_data.append({
                "간호사": name,
                "직전 4주 근무 이력 (근거)": hist_str,
                "패턴 권장": "D" if is_must_d else "E",
                "최종 확정": "D" if is_must_d else "E"
            })
        
        edited_slots = st.data_editor(pd.DataFrame(balancing_data), use_container_width=True)
        d_cnt = len(edited_slots[edited_slots["최종 확정"] == "D"])
        e_cnt = len(edited_slots[edited_slots["최종 확정"] == "E"])
        
        c1, c2 = st.columns(2)
        c1.metric("현재 D 슬롯", f"{d_cnt} / 4", delta=d_cnt-4, delta_color="inverse")
        c2.metric("현재 E 슬롯", f"{e_cnt} / 3", delta=e_cnt-3, delta_color="inverse")
        if d_cnt > 4: st.error("⚠️ D 슬롯 초과! 팀장님, 한 명을 E로 조정해 주세요.")

        # --- 2. 최적 병동 추천 로직 ---
        st.divider()
        st.subheader("2️⃣ 간호사별 최적 병동 추천")
        selected_nurse = st.selectbox("추천을 확인할 간호사 선택", nurses_1dong)
        allow_switch = st.checkbox("🚩 타 동(Building) 스위치 허용")
        
        if selected_nurse:
            confirmed_shift = edited_slots[edited_slots["간호사"] == selected_nurse]["최종 확정"].values[0]
            st.write(f"📌 **{selected_nurse}** 간호사: **{confirmed_shift}** 근무조 확정")
            
            # 차월 요청 병동 중 해당 근무조 필터링
            req_next = st.session_state.df_req_next
            avail_wards = req_next[req_next['계획근무조'] == confirmed_shift]['계획병동'].unique()
            
            # 누적 이력 기반 다양성 분석
            nurse_hist = df_master[df_master['성함'] == selected_nurse]
            ward_counts = nurse_hist.groupby('계획병동').size().to_dict()
            
            home_wards = WARD_GROUPS['1동']
            recommend_list = []
            for w in avail_wards:
                if not allow_switch and w not in home_wards: continue
                count = ward_counts.get(w, 0)
                last_visit = nurse_hist[nurse_hist['계획병동'] == w]['날짜'].max()
                recommend_list.append({
                    "병동": w, "소속": WARD_TO_BLD.get(w, "기타"),
                    "누적 방문일수": count, "마지막 방문일": last_visit if pd.notna(last_visit) else "미방문"
                })
            
            if recommend_list:
                rec_df = pd.DataFrame(recommend_list).sort_values(by=["누적 방문일수", "마지막 방문일"])
                st.write("**[추천 후보 및 근거 데이터]**")
                st.dataframe(rec_df, use_container_width=True)
                
                top_pick = rec_df.iloc[0]
                if top_pick['누적 방문일수'] == 0:
                    st.success(f"💡 최종 추천: **{top_pick['병동']}병동** (근거: 올해 한 번도 방문하지 않은 신규 병동입니다.)")
                else:
                    st.warning(f"💡 최종 추천: **{top_pick['병동']}병동** (근거: 모든 곳을 경험했으나, 누적 방문 횟수가 가장 적은 병동입니다.)")
            else:
                st.error("해당 조건에 맞는 지원 요청 병동이 없습니다.")
    else:
        st.info("파일 업로드와 2단계 분석을 먼저 완료해 주세요.")
