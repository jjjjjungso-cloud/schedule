import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 페이지 설정 ---
st.set_page_config(page_title="프라임 데이터 정합성 검증", layout="wide")

# --- [정제 함수] 배정표(계획) 확장 ---
def expand_plan_data(df):
    expanded_list = []
    # 필수 컬럼 확인
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    if not all(col in df.columns for col in required):
        return pd.DataFrame()

    for _, row in df.iterrows():
        try:
            start_dt = pd.to_datetime(row['시작일'])
            end_dt = pd.to_datetime(row['종료일'])
            curr = start_dt
            while curr <= end_dt:
                expanded_list.append({
                    '날짜': curr,
                    '성함': str(row['간호사 성함']).strip(),
                    '계획근무조': row['근무조'],
                    '계획병동': str(row['배정병동'])
                })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list).drop_duplicates()

# --- [정제 함수] 실제 근무표 정제 (P-코드 추출) ---
def clean_actual_data(uploaded_file, year):
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    
    for sheet_name in xl.sheet_names:
        m_match = re.findall(r'\d+', sheet_name)
        if not m_match: continue
        month_int = int(m_match[0])
        
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

# --- 메인 UI ---
st.title("🏥 프라임 데이터 통합 정합성 검증")
st.markdown("파일을 하나로 합치셨으므로, 이제 통합된 데이터를 기준으로 분석을 시작합니다.")

# 사이드바 설정
st.sidebar.header("📅 설정")
selected_year = st.sidebar.selectbox("기준 연도", [2026, 2027], index=0)

if 'master_df' not in st.session_state: st.session_state.master_df = None

# 1. 파일 업로드
st.header("1️⃣ 통합 데이터 업로드")
col1, col2 = st.columns(2)
with col1:
    file_p = st.file_uploader("계획표(Plan) 파일", type="xlsx")
with col2:
    file_a = st.file_uploader("근무표(Actual) 파일", type="xlsx")

# 2. 데이터 처리 및 비교
if file_p and file_a:
    if st.button("🚀 데이터 정제 및 비교 분석 실행"):
        # 1) 계획 데이터 정제
        df_plan = expand_plan_data(pd.read_excel(file_p))
        
        # 2) 실제 데이터 정제
        df_actual = clean_actual_data(file_a, selected_year)
        
        # 3) 두 데이터 병합 (날짜와 성함 기준)
        # 계획(Outer)을 기준으로 실제 데이터를 붙입니다.
        merged = pd.merge(df_plan, df_actual, on=['날짜', '성함'], how='left')
        
        # 4) 불일치 여부 체크 로직
        def check_diff(row):
            if pd.isna(row['실제병동']): return "실제기록없음"
            if row['계획병동'] != row['실제병동']: return "병동불일치"
            return "일치"
        
        merged['상태'] = merged.apply(check_diff, axis=1)
        st.session_state.master_df = merged
        st.success("데이터 분석이 완료되었습니다!")

# 3. 월별 탭 조회 및 결과 표시
if st.session_state.master_df is not None:
    st.header("2️⃣ 월별 분석 결과")
    
    df = st.session_state.master_df
    available_months = sorted(df['날짜'].dt.month.unique())
    month_tabs = st.tabs([f"{m}월" for m in available_months])
    
    for i, m in enumerate(available_months):
        with month_tabs[i]:
            m_df = df[df['날짜'].dt.month == m].copy()
            m_df['날짜'] = m_df['날짜'].dt.strftime('%Y-%m-%d')
            
            # 요약 지표
            c1, c2, c3 = st.columns(3)
            c1.metric("전체 계획 건수", f"{len(m_df)}건")
            c2.metric("병동 불일치", f"{len(m_df[m_df['상태']=='병동불일치'])}건")
            c3.metric("기록 누락", f"{len(m_df[m_df['상태']=='실제기록없음'])}건")
            
            # 데이터프레임 스타일링 (불일치 빨간색 강조)
            def highlight_diff(val):
                color = 'red' if val == '병동불일치' else ('orange' if val == '실제기록없음' else 'black')
                return f'color: {color}'

            st.dataframe(
                m_df.style.applymap(highlight_diff, subset=['상태']),
                use_container_width=True,
                height=500
            )
            
            # 다운로드 버튼
            csv = m_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(f"📥 {m}월 결과 다운로드", csv, f"prime_result_{m}월.csv", "text/csv")
