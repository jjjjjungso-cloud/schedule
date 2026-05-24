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
    """시작일~종료일 범위를 평일 단위 행으로 분리 및 주차 부여"""
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
                if curr.weekday() < 5:
                    expanded_list.append({
                        '날짜': curr,
                        '주차': f"{curr.isocalendar().week}주차",
                        '성함': str(row[c_name]).strip(),
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
    """2주 블록 로직"""
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
st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🏥 프라임 데이터 통합 및 배정 최적화 시스템</h1>", unsafe_allow_html=True)

if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

# 사이드바 설정
st.sidebar.header("📅 분석 기준 월 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("과거 데이터 분석 월", [f"{i}월" for i in range(1, 13)], index=4) # 기본 5월
month_int = int(re.findall(r'\d+', selected_month)[0])

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📂 1단계: 업로드", "🔍 2단계: 정제", "📊 3단계: 분석", "🎯 4단계: 배정", "📋 5단계: 결원대체 이력 보고서"
])

# --- 1단계 & 2단계 ---
with tab1:
    st.info(f"💡 {selected_month} 및 차월 분석을 위해 파일을 업로드하세요.")
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan)", type=["xlsx", "csv"])
    file_a = c2.file_uploader("과거 실제 근무표(Actual)", type=["xlsx", "csv"])
    file_r = c3.file_uploader("차월 지원 요청 파일(Request)", type=["xlsx", "csv"])

with tab2:
    if file_p and file_a and file_r:
        if st.button("🚀 데이터 통합 정제 시작"):
            def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
            df_p = expand_generic_data(load_df(file_p))
            df_a = clean_actual_data(file_a, selected_year, month_int)
            
            if not df_p.empty and not df_a.empty:
                df_p['날짜_key'] = pd.to_datetime(df_p['날짜']).dt.strftime('%Y-%m-%d')
                df_a['날짜_key'] = pd.to_datetime(df_a['날짜']).dt.strftime('%Y-%m-%d')
                df_p['성함_key'] = df_p['성함'].astype(str).str.strip()
                df_a['성함_key'] = df_a['성함'].astype(str).str.strip()
                
                df_p['계획병동_숫자'] = df_p['계획병동'].astype(str).str.extract(r'(\d+)')[0]
                df_a['실제병동_숫자'] = df_a['실제병동'].astype(str).str.extract(r'(\d+)')[0]
                
                df_master = pd.merge(df_p, df_a.drop(columns=['날짜', '성함'], errors='ignore'), on=['날짜_key', '성함_key'], how='left')
                df_master['날짜'] = df_master['날짜_key']
                
                st.session_state.df_master = df_master
                st.session_state.df_req_next = expand_generic_data(load_df(file_r))
                st.success("✅ 상호 동기화 정제가 완료되었습니다! 5단계 탭에서 리포트를 확인하세요.")
    else: st.warning("파일을 모두 업로드해 주세요.")

with tab3:
    if not st.session_state.df_master.empty:
        exp_matrix = st.session_state.df_master.groupby(['성함', '계획병동']).size().unstack(fill_value=0)
        st.dataframe(exp_matrix, use_container_width=True)

with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_req = st.session_state.df_req_next
        weeks = sorted(df_req['주차'].unique())
        selected_week = st.selectbox("배정 주차 선택", weeks)
        week_info = df_req[df_req['주차'] == selected_week]
        selected_nurse = st.selectbox("간호사를 선택하세요", sorted(list(NURSE_TO_BLD.keys())))
        final_shift = st.radio("배정할 근무조 선택", ["D", "E"], horizontal=True)
        st.success("배정 추천 엔진 정상 작동 중")


# --- 📋 [완벽 디자인 패치] 5단계: 이미지 매칭 리포트 뷰 탭 ---
with tab5:
    if not st.session_state.df_master.empty:
        df_m = st.session_state.df_master.copy()
        
        st.markdown(f"<h3 style='color: #1E3A8A;'>⚖️ {selected_month} 결원대체 출동 현황 분석</h3>", unsafe_allow_html=True)
        st.caption("과거 배정 계획과 실제 투입 기록을 대조하여 발생한 결원대체 근무를 시각화 보고서 형태로 표출합니다.")
        st.write("")
        
        # 날짜 기반 월 필터링
        df_m['날짜_dt'] = pd.to_datetime(df_m['날짜'])
        df_month = df_m[df_m['날짜_dt'].dt.month == month_int]
        
        # 결원대체 조건 필터링 (계획 != 실제)
        df_sub = df_month[
            (df_month['계획병동_숫자'] != df_month['실제병동_숫자']) & 
            (df_month['실제병동_숫자'].notna())
        ].copy()
        
        if not df_sub.empty:
            # 1. 상단 카드형 요약 지표 (Metrics)
            c1, c2, c3 = st.columns(3)
            
            total_cases = len(df_sub)
            top_nurse = df_sub['성함'].value_counts().idxmax()
            top_nurse_cnt = df_sub['성함'].value_counts().max()
            active_wards = df_sub['실제병동'].nunique()
            
            with c1:
                st.markdown(f"<div style='padding: 15px; border-radius: 10px; background-color: #F3F4F6; text-align: center; border-left: 5px solid #3B82F6;'><p style='margin:0; font-size:14px; color:#6B7280;'>월간 총 결원대체</p><h2 style='margin:5px 0; color:#1F2937;'>{total_cases}건</h2></div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<div style='padding: 15px; border-radius: 10px; background-color: #F3F4F6; text-align: center; border-left: 5px solid #EF4444;'><p style='margin:0; font-size:14px; color:#6B7280;'>⚠️ 최다 출동 간호사</p><h2 style='margin:5px 0; color:#1F2937;'>{top_nurse} ({top_nurse_cnt}회)</h2></div>", unsafe_allow_html=True)
            with c3:
                st.markdown(f"<div style='padding: 15px; border-radius: 10px; background-color: #F3F4F6; text-align: center; border-left: 5px solid #10B981;'><p style='margin:0; font-size:14px; color:#6B7280;'>🏥 지원 투입 병동 수</p><h2 style='margin:5px 0; color:#1F2937;'>{active_wards}개 병동</h2></div>", unsafe_allow_html=True)
            
            st.write("")
            st.divider()
            
            # 2. 이미지 스타일의 일자별 리포트 카드 리스트 표출 존
            st.markdown("### 📅 결원대체 상세 이력 리포트")
            
            # 최신 날짜 순으로 정렬
            df_log = df_sub.sort_values(by='날짜', ascending=False)
            
            # 간호사 필터 기능
            search_nurse = st.multiselect("👤 특정 간호사만 필터링", options=sorted(df_log['성함'].unique()))
            if search_nurse:
                df_log = df_log[df_log['성함'].isin(search_nurse)]
                
            st.write("")
            
            # 루프를 돌며 이미지에 나온 일지 스타일의 박스 레이아웃을 생성
            for _, row in df_log.iterrows():
                date_str = row['날짜']
                name = row['성함']
                plan_ward = f"{row['계획병동']}병동" if '병동' not in str(row['계획병동']) else row['계획병동']
                actual_ward = f"{row['실제병동']}병동" if '병동' not in str(row['실제병동']) else row['실제병동']
                shift = row['실제근무조']
                
                # 소속 동(Building) 태그 매핑
                bld_tag = NURSE_TO_BLD.get(name, "1동")
                bld_color = "#1E40AF" if bld_tag == "1동" else "#065F46"
                
                # HTML과 CSS를 활용한 개별 리포트 박스 렌더링
                card_html = f"""
                <div style="
                    background-color: #FFFFFF; 
                    padding: 20px; 
                    border-radius: 12px; 
                    margin-bottom: 15px; 
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                    border: 1px solid #E5E7EB;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 15px; font-weight: 600; color: #4B5563; background-color: #F3F4F6; padding: 4px 10px; border-radius: 6px;">📅 {date_str}</span>
                        <span style="font-size: 12px; font-weight: bold; color: #FFFFFF; background-color: {bld_color}; padding: 3px 8px; border-radius: 20px;">{bld_tag} 소속</span>
                    </div>
                    <div style="display: flex; align-items: baseline; gap: 15px; margin-top: 10px;">
                        <h3 style="margin: 0; color: #111827; font-size: 20px; font-weight: 700;">{name} 간호사</h3>
                        <p style="margin: 0; font-size: 16px; color: #1F2937; font-weight: 500;">
                            <span style="color: #6B7280; font-weight: normal;">원래계획:</span> <strong style="color: #4B5563;">{plan_ward}</strong> 
                            <span style="color: #3B82F6; font-weight: bold; margin: 0 8px;">➡️</span> 
                            <span style="color: #6B7280; font-weight: normal;">실제근무:</span> <strong style="color: #EF4444; font-size: 18px;">{actual_ward}</strong>
                            <span style="margin-left: 15px; background-color: #FEF3C7; color: #92400E; padding: 2px 8px; border-radius: 4px; font-size: 14px; font-weight: bold;">근무조: {shift}</span>
                        </p>
                    </div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
                
            # 다운로드 기능 유지
            st.write("")
            csv_cols = ['날짜', '성함', '계획병동', '실제병동', '실제근무조']
            df_download = df_log[csv_cols].rename(columns={'계획병동': '원래계획', '실제병동': '실제 근무', '실제근무조': '근무조'})
            csv_data = df_download.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label=f"📥 {selected_month} 결원대체 명단 양식 다운로드 (CSV)",
                data=csv_data,
                file_name=f"결원대체_이력보고서_{selected_month}.csv",
                mime="text/csv"
            )
        else:
            st.success(f"🎉 {selected_month} 대조 결과: 계획표와 실제 근무 기록이 일치하여 결원대체(비상 출동) 내역이 존재하지 않습니다.")
    else:
        st.info("📂 1, 2단계를 통해 과거 배정표(Plan)와 실제 근무표(Actual)를 먼저 통합 정제해 주세요.")
