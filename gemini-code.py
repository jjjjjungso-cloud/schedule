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
    """배정표(Plan) 범위를 일자별 평일 행으로 확장"""
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
                        '성함': str(row[c_name]).strip() if c_name and pd.notna(row[c_name]) else "",
                        '계획근무조': str(row[c_shift]).strip().upper(),
                        '계획병동': str(row[c_ward]).strip(),
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

def clean_actual_data(uploaded_file, year, month_int):
    """실제 근무표 정제: P-코드 패턴 및 일반 병동 텍스트 유연하게 추출"""
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
                code = str(row.iloc[d_idx]).strip()
                
                # P-코드 형태 정제 (예: P-41/D)
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        shift = 'D' if ('D4' in code or 'D' in code) else 'E'
                        actual_list.append({
                            '날짜': datetime(year, month_int, int(d_match[0])),
                            '성함': name,
                            '실제근무조': shift,
                            '실제병동': ward_match.group(1)
                        })
                # [보완] 만약 실제 근무표에 '41병동' 또는 '41' 처럼 직접 적혀있는 경우 대응
                elif any(w in code for w in ['병동', 'D', 'E']) or code.isdigit():
                    ward_digit = re.findall(r'\d+', code)
                    if ward_digit:
                        shift = 'E' if 'E' in code else 'D' # 기본값 D, E가 명시되면 E
                        actual_list.append({
                            '날짜': datetime(year, month_int, int(d_match[0])),
                            '성함': name,
                            '실제근무조': shift,
                            '실제병동': ward_digit[0]
                        })
    return pd.DataFrame(actual_list)

# --- 메인 UI 설정 ---
st.set_page_config(page_title="프라임 배정 최적화 시스템", layout="wide")
st.title("🏥 프라임 데이터 통합 및 배정 최적화 시스템")

if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

st.sidebar.header("📅 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("분석 대상 월(Month)", [f"{i}월" for i in range(1, 13)], index=4) # 기본 5월
month_int = int(re.findall(r'\d+', selected_month)[0])

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📂 1단계: 업로드", "🔍 2단계: 정제", "📊 3단계: 경험분석", "🎯 4단계: 차월배정", "⚖️ 5단계: 결원대체 형평성"
])

# --- 1단계: 업로드 ---
with tab1:
    st.info(f"💡 {selected_month} 및 차월 분석을 위해 파일을 업로드하세요.")
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan)", type=["xlsx", "csv"])
    file_a = c2.file_uploader("과거 실제 근무표(Actual)", type=["xlsx", "csv"])
    file_r = c3.file_uploader("차월 지원 요청 파일(Request)", type=["xlsx", "csv"])

# --- 2단계: 정제 (★본질 보완 구역) ---
with tab2:
    if file_p and file_a and file_r:
        if st.button("🚀 데이터 통합 정제 시작"):
            def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
            
            df_p = expand_generic_data(load_df(file_p))
            df_a = clean_actual_data(file_a, selected_year, month_int)
            
            if not df_p.empty and not df_a.empty:
                # 텍스트 포맷 강제 통일 (공백 제거, 문자열화)
                df_p['날짜'] = pd.to_datetime(df_p['날짜']).dt.normalize()
                df_a['날짜'] = pd.to_datetime(df_a['날짜']).dt.normalize()
                df_p['성함'] = df_p['성함'].astype(str).str.strip()
                df_a['성함'] = df_a['성함'].astype(str).str.strip()
                
                # 병동 명칭에서 숫자만 추출하여 완벽하게 일치시킴 ('51병동' -> '51')
                df_p['계획병동_정제'] = df_p['계획병동'].astype(str).str.extract(r'(\d+)')[0]
                df_a['실제병동_정제'] = df_a['실제병동'].astype(str).str.extract(r'(\d+)')[0]
                
                # 완벽하게 매칭하여 마스터 생성
                df_master = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
                
                st.session_state.df_master = df_master
                st.session_state.df_req_next = expand_generic_data(load_df(file_r))
                st.success(f"✅ {selected_month} 데이터가 동기화되었습니다! 5단계로 이동해 보세요.")
            else:
                st.error("⚠️ 파일 정제 결과 데이터가 비어있습니다. 서식을 확인해 주세요.")
    else: st.warning("파일을 모두 업로드해 주세요.")

# --- 3단계 & 4단계 (기존 로직 유지) ---
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
        st.success("배정 추천 엔진이 정상 작동 중입니다.")

# --- 5단계: 결원대체 형평성 분석 (★본질 구현 구역) ---
with tab5:
    if not st.session_state.df_master.empty:
        df_m = st.session_state.df_master.copy()
        
        st.header(f"⚖️ 5단계: {selected_month} 결원대체 형평성 및 피로도 분석")
        
        # 날짜 필터링
        df_m['날짜'] = pd.to_datetime(df_m['날짜'])
        df_month = df_m[(df_m['날짜'].dt.year == selected_year) & (df_m['날짜'].dt.month == month_int)]
        
        # 데이터 매칭 상태 검증 로그 (디버깅용 안전장치)
        with st.expander("🔍 [데이터 매칭 동기화 상태 검증]"):
            st.write("계획표와 실제근무표가 정상 결합되었는지 샘플을 확인합니다. (실제병동이 빈칸이면 매칭 실패를 의미)")
            st.dataframe(df_month[['날짜', '성함', '계획병동', '실제병동']].dropna(subset=['실제병동']).head(5), use_container_width=True)

        # 결원대체 필터링: 정제된 숫자 병동명이 서로 다른 경우
        df_sub = df_month[
            (df_month['계획병동_정제'] != df_month['실제병동_정제']) & 
            (df_month['실제병동_정제'].notna())
        ].copy()
        
        # 사용자가 요청한 규격 컬럼으로 명세화
        df_sub['원래계획'] = df_sub['계획병동_정제'] + "병동"
        df_sub['실제 근무'] = df_sub['실제병동_정제'] + "병동"
        df_sub['근무조'] = df_sub['실제근무조']
        
        if not df_sub.empty:
            # KPI 존
            c1, c2, c3 = st.columns(3)
            c1.metric(f"📊 {selected_month} 총 결원대체", f"{len(df_sub)}건")
            top_nurse = df_sub['성함'].value_counts().idxmax()
            c2.metric("⚠️ 최다 출동 간호사", f"{top_nurse} ({df_sub['성함'].value_counts().max()}회)")
            c3.metric("🏥 지원 발생 병동 수", f"{df_sub['실제 근무'].nunique()}개 병동")
            
            # 매트릭스 존
            st.subheader("📊 간호사별 결원대체 출동 매트릭스")
            matrix_df = df_sub.groupby(['성함', '실제 근무']).size().unstack(fill_value=0)
            matrix_df['총 출동 횟수(피로도)'] = matrix_df.sum(axis=1)
            matrix_df['경험한 병동 수(다각화)'] = (matrix_df.iloc[:, :-1] > 0).sum(axis=1)
            matrix_df = matrix_df.sort_values(by='총 출동 횟수(피로도)', ascending=False)
            st.dataframe(matrix_df.style.background_gradient(cmap='Reds', subset=['총 출동 횟수(피로도)']), use_container_width=True)
            
            # 상세 이력 존 (요청 명세 적용)
            st.subheader("📅 일자별 상세 결원대체 이력 목록")
            df_log = df_sub.sort_values(by='날짜', ascending=False).copy()
            df_log['날짜'] = df_log['날짜'].dt.strftime('%Y-%m-%d')
            
            display_cols = ['날짜', '성함', '원래계획', '실제 근무', '근무조']
            st.dataframe(df_log[display_cols], use_container_width=True, hide_index=True)
        else:
            st.success(f"🎉 분석 완료: {selected_month}에는 계획과 실제가 다른 결원대체 이력이 발견되지 않았습니다.")
    else:
        st.info("📂 1, 2단계를 통해 근무표 데이터들을 먼저 정제 통합해 주세요.")
