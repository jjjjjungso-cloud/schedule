import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [설정 데이터] 팀장님이 관리하는 구역 ---
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
    
    if not all(any(req in c for c in df.columns) for req in required):
        return pd.DataFrame()
    
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
                if curr.weekday() < 5: # 평일만
                    expanded_list.append({
                        '날짜': curr,
                        '주차': f"{curr.isocalendar().week}주차",
                        '성함': str(row[c_name]).strip() if c_name and pd.notna(row[c_name]) else "",
                        '계획근무조': str(row[c_shift]).strip(),
                        '계획병동': str(row[c_ward]).strip(),
                        '시작일': start_dt.strftime('%Y-%m-%d'),
                        '종료일': end_dt.strftime('%Y-%m-%d')
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

def recommend_shift_logic(history_list):
    """2주 블록 로직: 마지막 근무조가 1주면 유지, 2주면 교대"""
    if not history_list: return "D"
    last_shift = history_list[-1]
    count = 0
    for s in reversed(history_list):
        if s == last_shift: count += 1
        else: break
    return last_shift if count < 2 else ("D" if last_shift == "E" else "E")

def get_recent_history_list(df, nurse_name, target_date):
    """직전 5주간의 근무조 리스트 추출"""
    if df.empty: return []
    target_dt = pd.to_datetime(target_date)
    start_dt = target_dt - timedelta(weeks=5)
    hist = df[(df['성함'] == nurse_name) & (df['날짜'] >= start_dt) & (df['날짜'] < target_dt)]
    if hist.empty: return []
    return hist.sort_values('날짜').groupby('주차')['계획근무조'].first().tolist()


# --- 메인 UI 설정 ---
st.set_page_config(page_title="프라임 배정 최적화 시스템", layout="wide")
st.title("🏥 프라임 데이터 통합 및 배정 최적화 시스템")

# 세션 스테이트 초기화 (탭 간 데이터 공유용)
if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

# 사이드바 설정 (기준 월을 바꾸면 대시보드 전체가 반응함)
st.sidebar.header("📅 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("분석 대상 월(Month)", [f"{i}월" for i in range(1, 13)], index=4) # 기본 5월
month_int = int(re.findall(r'\d+', selected_month)[0])

# 탭 구성 (5단계 추가 완료)
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📂 1단계: 업로드", 
    "🔍 2단계: 정제", 
    "📊 3단계: 경험분석", 
    "🎯 4단계: 차월배정", 
    "⚖️ 5단계: 결원대체 형평성"
])

# --- 1단계: 업로드 ---
with tab1:
    st.info(f"💡 {selected_month} 및 차월 배정 분석을 위해 아래 3가지 파일을 모두 업로드하세요.")
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan) 선택", type=["xlsx", "csv"])
    file_a = c2.file_uploader("과거 실제 근무표(Actual) 선택", type=["xlsx", "csv"])
    file_r = c3.file_uploader("차월 지원 요청 파일(Request) 선택", type=["xlsx", "csv"])

# --- 2단계: 정제 ---
with tab2:
    if file_p and file_a and file_r:
        if st.button("🚀 데이터 통합 정제 시작"):
            def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
            
            # 과거 계획 및 실제 데이터 정제 후 결합
            df_p = expand_generic_data(load_df(file_p))
            df_a = clean_actual_data(file_a, selected_year, month_int)
            
            # 마스터 데이터 상태 저장
            st.session_state.df_master = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
            st.session_state.df_req_next = expand_generic_data(load_df(file_r))
            st.success(f"✅ {selected_month} 데이터 통합 정제 완료! 3, 4, 5단계 탭으로 이동하여 분석을 확인하세요.")
    else: 
        st.warning("⚠️ 1단계 탭에서 파일을 모두 업로드해 주세요.")

# --- 3단계: 분석 (경험 매트릭스) ---
with tab3:
    if not st.session_state.df_master.empty:
        st.subheader("🕵️‍♀️ 간호사별 병동 지원 일수 (경험 매트릭스)")
        exp_matrix = st.session_state.df_master.groupby(['성함', '계획병동']).size().unstack(fill_value=0)
        st.dataframe(exp_matrix, use_container_width=True)
    else: 
        st.info("📂 2단계를 먼저 실행하여 데이터를 정제해 주세요.")

# --- 4단계: 배정 의사결정 ---
with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_master = st.session_state.df_master
        df_req = st.session_state.df_req_next
        
        st.header("🎯 차월 배정 의사결정")

        weeks = sorted(df_req['주차'].unique())
        selected_week = st.selectbox("배정 주차 선택", weeks)
        week_info = df_req[df_req['주차'] == selected_week]
        date_range = f"{week_info['날짜'].min().strftime('%Y-%m-%d')} ~ {week_info['날짜'].max().strftime('%Y-%m-%d')}"
        st.subheader(f"📅 {selected_week} ({date_range})")

        all_nurses = sorted(list(NURSE_TO_BLD.keys()))
        selected_nurse = st.selectbox("간호사를 선택하세요", all_nurses)
        
        st.divider()
        col_logic, col_select = st.columns(2)
        with col_logic:
            st.subheader("⚙️ 근무조 패턴 분석")
            hist_list = get_recent_history_list(df_master, selected_nurse, week_info['날짜'].min())
            rec_shift = recommend_shift_logic(hist_list)
            st.write(f"📌 **{selected_nurse}** 직전 이력: `{ ' -> '.join(hist_list) if hist_list else '데이터 없음' }`")
            st.info(f"💡 **패턴 분석 결과:** 차주 추천 근무는 **{rec_shift}**입니다.")
        
        with col_select:
            st.subheader("⌨️ 근무조 최종 선택")
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
                st.success(f"🏆 최종 추천: **{top['병동']}병동** (누적 방문 {top['누적 방문일수']}회로 가장 적음)")
            else: st.warning(f"{my_bld} 내 지원 요청이 없습니다. 스위치를 허용해 보세요.")
        else: st.error(f"해당 주차에 {final_shift} 근무조 요청이 없습니다.")
    else: 
        st.info("📂 1, 2단계를 먼저 완료해 주세요.")

# --- 5단계: 결원대체 형평성 및 피로도 분석 (NEW) ---
with tab5:
    if not st.session_state.df_master.empty:
        # 데이터 카피 후 날짜 인덱싱 안전화
        df_m = st.session_state.df_master.copy()
        df_m['날짜'] = pd.to_datetime(df_m['날짜'])
        
        st.header(f"⚖️ 5단계: {selected_month} 결원대체 형평성 및 간호사 피로도 분석")
        st.info(f"💡 {selected_month}의 원래 계획된 병동과 실제 근무한 병동이 다른 '결원대체(비상 출동)' 이력을 확인하고 균형적인 인력 분배를 검증합니다.")
        
        # 1. 사이드바에서 선택한 연도/월 데이터만 정확하게 1차 필터링
        df_month_filtered = df_m[
            (df_m['날짜'].dt.year == selected_year) & 
            (df_m['날짜'].dt.month == month_int)
        ]
        
        # 2. 계획병동과 실제병동이 다르고 실제 데이터가 있는 것만 발라내기 (결원대체 조건)
        df_sub = df_month_filtered[
            (df_month_filtered['계획병동'] != df_month_filtered['실제병동']) & 
            (df_month_filtered['실제병동'].notna())
        ].copy()
        
        # 3. 요청하신 컴포넌트 규격에 맞춰 컬럼 매핑 및 네이밍 정규화
        df_sub['원래계획'] = df_sub['계획병동'] + "병동"
        df_sub['실제 근무'] = df_sub['실제병동'] + "병동"
        df_sub['근무조'] = df_sub['실제근무조']
        
        if not df_sub.empty:
            # --- [KPI 대시보드 존] ---
            c1, c2, c3 = st.columns(3)
            
            total_cnt = len(df_sub)
            c1.metric(f"📊 {selected_month} 총 결원대체 건수", f"{total_cnt}건")
            
            top_nurse = df_sub['성함'].value_counts().idxmax()
            top_nurse_cnt = df_sub['성함'].value_counts().max()
            c2.metric("⚠️ 최다 출동 간호사 (피로도 집중)", f"{top_nurse} ({top_nurse_cnt}회)")
            
            unique_wards = df_sub['실제 근무'].nunique()
            c3.metric("🏥 지원 발생 병동 수", f"{unique_wards}개 병동")
            
            st.divider()
            
            # --- [시각화 매트릭스 존] ---
            st.subheader(f"📊 {selected_month} 간호사별 출동 매트릭스")
            st.caption("간호사별 편중 현상이 없는지 확인하세요. (적색: 피로도 누적 위험 / 청색: 다양한 임상경험 축적)")
            
            # 교차 피벗 테이블 생성
            matrix_df = df_sub.groupby(['성함', '실제 근무']).size().unstack(fill_value=0)
            
            # 파악용 통계 컬럼 우측 배치
            matrix_df['총 출동 횟수(피로도)'] = matrix_df.sum(axis=1)
            matrix_df['경험한 병동 수(다각화)'] = (matrix_df.iloc[:, :-1] > 0).sum(axis=1)
            
            # 출동 횟수가 많은 과부하 순서로 상단 정렬
            matrix_df = matrix_df.sort_values(by='총 출동 횟수(피로도)', ascending=False)
            
            # Streamlit 내장 스타일링 (히트맵 효과 연출)
            st.dataframe(
                matrix_df.style.background_gradient(cmap='Reds', subset=['총 출동 횟수(피로도)'])
                               .background_gradient(cmap='Blues', subset=['경험한 병동 수(다각화)']),
                use_container_width=True
            )
            
            st.divider()
            
            # --- [상세 로그 및 리포트 존] ---
            st.subheader(f"📅 {selected_month} 상세 결원대체 이력 목록")
            
            # 날짜 내림차순 정렬 및 깔끔한 날짜 텍스트 처리
            df_log = df_sub.sort_values(by='날짜', ascending=False).copy()
            df_log['날짜'] = df_log['날짜'].dt.strftime('%Y-%m-%d')
            
            # 관리자 요청 명세 컬럼 레이아웃
            display_cols = ['날짜', '성함', '원래계획', '실제 근무', '근무조']
            
            # 특정 간호사 검색 필터 탑재
            filter_nurse = st.multiselect("원하는 간호사 이력만 필터링", options=sorted(df_log['성함'].unique()))
            if filter_nurse:
                df_log = df_log[df_log['성함'].isin(filter_nurse)]
                
            st.dataframe(df_log[display_cols], use_container_width=True, hide_index=True)
            
            # --- [간호부 장표 제출용 다운로드] ---
            csv_data = df_log[display_cols].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label=f"📥 {selected_month} 결원대체 보고서 다운로드 (CSV)",
                data=csv_data,
                file_name=f"결원대체_분석보고서_{selected_year}년_{selected_month}.csv",
                mime="text/csv"
            )
        else:
            st.success(f"🎉 🎉 분석 결과: {selected_month}에는 계획과 다르게 움직인 결원대체 비상 근무가 0건입니다! 안정적인 한 달이었습니다.")
    else:
        st.info("📂 1, 2단계를 통해 과거 배정표(Plan)와 실제 근무표(Actual)를 먼저 통합 정제해 주세요.")
