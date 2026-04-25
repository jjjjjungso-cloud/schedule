import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 페이지 설정 ---
st.set_page_config(page_title="프라임 통합 검증 시스템", layout="wide")

# --- [정제 함수] 배정표(계획): 제목이 없어도 컬럼 순서로 읽기 ---
def expand_plan_master_v2(uploaded_file):
    xl = pd.ExcelFile(uploaded_file)
    combined_list = []
    
    for sheet_name in xl.sheet_names:
        # 데이터 읽기 (제목이 없을 수 있으므로 header=None으로 일단 읽음)
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)
        
        # 만약 첫 행이 '시작일' 같은 텍스트라면 그 행은 버림
        if '시작' in str(df.iloc[0, 0]):
            df = df.iloc[1:].reset_index(drop=True)
            
        for _, row in df.iterrows():
            try:
                # 컬럼 순서 고정: 0(A)=시작일, 1(B)=종료일, 2(C)=근무조, 3(D)=병동, 4(E)=이름
                start_dt = pd.to_datetime(row[0])
                end_dt = pd.to_datetime(row[1])
                
                curr = start_dt
                while curr <= end_dt:
                    combined_list.append({
                        '날짜': curr,
                        '성함': str(row[4]).strip(),
                        '계획근무조': str(row[2]).strip(),
                        '계획병동': str(int(row[3])) # 병동 번호를 숫자로 변환 후 문자로
                    })
                    curr += timedelta(days=1)
            except: continue
            
    return pd.DataFrame(combined_list).drop_duplicates()

# --- [정제 함수] 실제 근무표: 시트명에서 월 추출 로직 강화 ---
def clean_actual_master_v2(uploaded_file, year):
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    
    for sheet_name in xl.sheet_names:
        # 시트 이름에서 1~12 사이의 숫자(월)만 추출
        nums = re.findall(r'\d+', sheet_name)
        month_int = next((int(n) for n in nums if 1 <= int(n) <= 12), None)
        
        if month_int is None: continue
        
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        # '명'이 들어간 열(이름), '일'이 들어간 열(날짜) 자동 찾기
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

# --- 메인 대시보드 ---
st.title("🏥 프라임 데이터 통합 정합성 검증")

# 사이드바
selected_year = st.sidebar.selectbox("기준 연도", [2026, 2027], index=0)

if 'final_df' not in st.session_state: st.session_state.final_df = None

t1, t2, t3 = st.tabs(["📂 파일 업로드", "⚙️ 통합 분석", "📊 결과 조회"])

with t1:
    col_p, col_a = st.columns(2)
    with col_p:
        file_p = st.file_uploader("통합 배정표(2026년 시트 포함)", type="xlsx")
    with col_a:
        file_a = st.file_uploader("실제 근무표(월별 시트 포함)", type="xlsx")

with t2:
    if file_p and file_a:
        if st.button("🚀 정합성 분석 시작"):
            with st.spinner("데이터를 매칭 중입니다..."):
                # 1. 계획/실제 정제
                df_p = expand_plan_master_v2(file_p)
                df_a = clean_actual_master_v2(file_a, selected_year)
                
                if df_p.empty or df_a.empty:
                    st.error("데이터를 추출하지 못했습니다. 파일 형식을 확인해주세요.")
                else:
                    # 2. 병합
                    merged = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
                    
                    # 3. 상태 판별
                    def get_status(row):
                        if pd.isna(row['실제병동']): return "기록누락"
                        if row['계획병동'] != row['실제병동']: return "병동불일치"
                        return "일치"
                    
                    merged['검증결과'] = merged.apply(get_status, axis=1)
                    st.session_state.final_df = merged.sort_values(['날짜', '성함'])
                    st.success("✅ 분석 완료! 3단계 탭으로 이동하세요.")

with t3:
    if st.session_state.final_df is not None:
        df = st.session_state.final_df
        months = sorted(df['날짜'].dt.month.unique())
        tabs = st.tabs([f"{m}월" for m in months])
        
        for i, m in enumerate(months):
            with tabs[i]:
                m_df = df[df['날짜'].dt.month == m].copy()
                m_df['날짜'] = m_df['날짜'].dt.strftime('%Y-%m-%d')
                
                # 요약
                s1, s2, s3 = st.columns(3)
                s1.metric("전체 계획", f"{len(m_df)}건")
                s2.warning(f"병동 불일치: {len(m_df[m_df['검증결과']=='병동불일치'])}건")
                s3.error(f"기록 누락: {len(m_df[m_df['검증결과']=='기록누락'])}건")
                
                # 스타일링
                def color_result(val):
                    if val == '병동불일치': return 'background-color: #ffcccc; color: red'
                    if val == '기록누락': return 'background-color: #fff4e6; color: orange'
                    return ''
                
                st.dataframe(m_df.style.applymap(color_result, subset=['검증결과']), use_container_width=True)
    else:
        st.info("2단계에서 분석 버튼을 눌러주세요.")
