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

def expand_generic_data(df):
    """시작일~종료일 범위를 평일 단위 행으로 분리 및 주차 부여 (계획/지원요청 공통)"""
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동']
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
                        '성함': str(row.get('간호사 성함', '')).strip(),
                        '계획근무조': str(row['근무조']).strip(),
                        '계획병동': str(row['배정병동'])
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

def recommend_shift_logic(history_list):
    """2주 블록 로직: 마지막 근무조가 1주면 유지, 2주면 교대 (EEDDE -> E)"""
    if not history_list: return "D" # 데이터 없으면 D 시작 가상
    
    last_shift = history_list[-1]
    # 연속된 마지막 근무조의 주차 수 계산
    count = 0
    for s in reversed(history_list):
        if s == last_shift: count += 1
        else: break
    
    # 2주를 다 못 채웠으면 유지, 다 채웠으면 교대
    if count < 2: return last_shift
    else: return "D" if last_shift == "E" else "E"

def get_recent_history_list(df, nurse_name, target_date):
    """직전 5주간의 근무조 리스트 추출"""
    if df.empty: return []
    target_dt = pd.to_datetime(target_date)
    start_dt = target_dt - timedelta(weeks=5)
    hist = df[(df['성함'] == nurse_name) & (df['날짜'] >= start_dt) & (df['날짜'] < target_dt)]
    if hist.empty: return []
    # 주차별로 정렬하여 근무조 리스트 생성
    return hist.sort_values('날짜').groupby('주차')['계획근무조'].first().tolist()

# --- 메인 UI ---
st.set_page_config(page_title="프라임 배정 최적화 시스템", layout="wide")
st.title("🏥 프라임 데이터 통합 및 배정 최적화 시스템")

if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

tab1, tab2, tab3, tab4 = st.tabs([
    "📂 1단계: 파일 업로드", "🔍 2단계: 데이터 정제 및 검증", 
    "📊 3단계: 누적 데이터 분석", "🎯 4단계: 차월 배정 의사결정"
])

with tab1:
    st.info("💡 5월 배정 분석을 위해 3가지 파일을 업로드하세요.")
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan)", type=["xlsx", "csv"])
    file_a = c2.file_uploader("과거 실제 근무표(Actual)", type=["xlsx", "csv"])
    file_r = c3.file_uploader("차월 지원 요청 파일(Request - rev4)", type=["xlsx", "csv"])

with tab2:
    if file_p and file_a and file_r:
        if st.button("🚀 데이터 통합 정제 시작"):
            # 데이터 로드 (CSV/Excel 구분)
            def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
            
            # 계획 데이터 정제
            df_p = expand_generic_data(load_df(file_p))
            # 5월 지원 요청 정제 (주차별 확장)
            st.session_state.df_req_next = expand_generic_data(load_df(file_r))
            
            st.session_state.df_master = df_p # 실제 정합성 체크 생략(분석 중심)
            st.success("✅ 모든 데이터가 주차별로 정제되었습니다!")
            
            st.subheader("📋 5월 지원 필요 주차 현황")
            st.dataframe(st.session_state.df_req_next, use_container_width=True)

with tab3:
    if not st.session_state.df_master.empty:
        st.subheader("🕵️‍♀️ 간호사별 병동 지원 일수 (경험 매트릭스)")
        exp_matrix = st.session_state.df_master.groupby(['성함', '계획병동']).size().unstack(fill_value=0)
        st.dataframe(exp_matrix, use_container_width=True)
    else: st.info("2단계 분석을 먼저 실행하세요.")

with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_master = st.session_state.df_master
        df_req = st.session_state.df_req_next
        st.header("🎯 데이터 기반 5월 배정 의사결정")

        # 1. 간호사 필터 (1동/2동 통합 선택)
        nurse_list = sorted(list(NURSE_TO_BLD.keys()))
        selected_nurse = st.selectbox("간호사를 선택하세요", nurse_list)
        
        # 2. 근무조 슬롯 분석
        st.subheader("1️⃣ 근무조 패턴 분석 (2주 블록 기준)")
        hist_list = get_recent_history_list(df_master, selected_nurse, "2026-05-01")
        rec_shift = recommend_shift_logic(hist_list)
        
        st.write(f"📌 **{selected_nurse}** 간호사의 직전 이력: `{ ' -> '.join(hist_list) if hist_list else '데이터 없음' }`")
        st.info(f"💡 **분석 근거:** 마지막 근무조가 {'1주' if len(hist_list) > 0 and (len(hist_list) == 1 or hist_list[-1] != hist_list[-2]) else '2주'}간 유지되었으므로, 차주 추천 근무는 **{rec_shift}**입니다.")
        
        # 3. 병동 추천
        st.divider()
        st.subheader("2️⃣ 최적 병동 추천")
        allow_switch = st.checkbox("🚩 타 동(Building) 스위치 허용")
        
        # 선택된 날짜(주차) 필터
        target_week = st.selectbox("배정 주차 선택", sorted(df_req['주차'].unique()))
        avail_today = df_req[(df_req['주차'] == target_week) & (df_req['계획근무조'] == rec_shift)]
        
        if not avail_today.empty:
            my_bld = NURSE_TO_BLD.get(selected_nurse, "1동")
            visited = set(df_master[df_master['성함'] == selected_nurse]['계획병동'].unique())
            
            recommend_list = []
            for w in avail_today['계획병동'].unique():
                if not allow_switch and WARD_TO_BLD.get(w) != my_bld: continue
                counts = df_master[df_master['성함'] == selected_nurse].groupby('계획병동').size().get(w, 0)
                recommend_list.append({
                    "병동": w, "소속": WARD_TO_BLD.get(w, "기타"),
                    "누적 방문일수": counts, "경험여부": "가봄" if w in visited else "안가봄"
                })
            
            if recommend_list:
                res_df = pd.DataFrame(recommend_list).sort_values(by=["경험여부", "누적 방문일수"])
                st.dataframe(res_df, use_container_width=True)
                top = res_df.iloc[0]
                st.success(f"최종 추천: **{top['병동']}병동** ({top['경험여부']} 병동이며 누적 방문 {top['누적 방문일수']}회)")
            else: st.warning("조건에 맞는 병동이 없습니다. 스위치 허용을 고려해 보세요.")
        else: st.error(f"해당 주차({target_week})에 {rec_shift} 근무조 지원 요청이 없습니다.")
