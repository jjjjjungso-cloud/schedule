import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- UI 설정 ---
st.set_page_config(page_title="프라임 데이터 통합 정합성 검증", layout="wide")

# --- [유틸리티] 배정표(계획) 통합 및 확장 ---
def expand_plan_master(uploaded_file):
    xl = pd.ExcelFile(uploaded_file)
    combined_list = []
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        if not all(col in df.columns for col in required):
            continue
            
        for _, row in df.iterrows():
            try:
                start_dt = pd.to_datetime(row['시작일'])
                end_dt = pd.to_datetime(row['종료일'])
                curr = start_dt
                while curr <= end_dt:
                    combined_list.append({
                        '날짜': curr,
                        '성함': str(row['간호사 성함']).strip(),
                        '계획근무조': row['근무조'],
                        '계획병동': str(row['배정병동'])
                    })
                    curr += timedelta(days=1)
            except: continue
    return pd.DataFrame(combined_list).drop_duplicates()

# --- [유틸리티] 실제 근무표 정제 (P-코드 분석) ---
def clean_actual_master(uploaded_file, year):
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    
    for sheet_name in xl.sheet_names:
        # 시트 이름에서 숫자(월) 추출
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

# --- 메인 로직 ---
st.title("🏥 프라임 데이터 통합 정합성 검증 시스템")

# 세션 상태 초기화
if 'analyzed_df' not in st.session_state: st.session_state.analyzed_df = None

# 사이드바 설정
st.sidebar.header("📅 설정")
selected_year = st.sidebar.selectbox("기준 연도", [2026, 2027], index=0)

tab1, tab2, tab3 = st.tabs(["📂 1단계: 파일 업로드", "⚙️ 2단계: 통합 분석 실행", "📊 3단계: 월별 정합성 결과"])

with tab1:
    st.markdown("### 마스터 파일 업로드")
    col_p, col_a = st.columns(2)
    with col_p:
        file_p = st.file_uploader("통합 배정표(계획) 파일", type="xlsx", key="p_up")
    with col_a:
        file_a = st.file_uploader("통합 근무표(실제) 파일", type="xlsx", key="a_up")

with tab2:
    if file_p and file_a:
        st.info("💡 두 파일의 데이터를 대조하여 불일치 항목을 찾아냅니다.")
        if st.button("🚀 전체 데이터 통합 분석 실행"):
            # 1. 각각 정제
            df_plan = expand_plan_master(file_p)
            df_actual = clean_actual_master(file_a, selected_year)
            
            # 2. 데이터 병합 (날짜, 성함 기준)
            merged = pd.merge(df_plan, df_actual, on=['날짜', '성함'], how='left')
            
            # 3. 상태 판별 함수
            def check_status(row):
                if pd.isna(row['실제병동']): return "기록누락(P코드없음)"
                if row['계획병동'] != row['실제병동']: return "병동불일치"
                return "일치"
            
            merged['검증결과'] = merged.apply(check_status, axis=1)
            st.session_state.analyzed_df = merged.sort_values(['날짜', '성함'])
            st.success("✅ 분석 완료! 3단계 탭에서 결과를 확인하세요.")
    else:
        st.warning("파일을 먼저 업로드해 주세요.")

with tab3:
    if st.session_state.analyzed_df is not None:
        df = st.session_state.analyzed_df
        available_months = sorted(df['날짜'].dt.month.unique())
        
        # 월별 탭 생성
        month_tabs = st.tabs([f"{m}월" for m in available_months])
        
        for i, m in enumerate(available_months):
            with month_tabs[i]:
                m_df = df[df['날짜'].dt.month == m].copy()
                
                # 지표 표시
                c1, c2, c3 = st.columns(3)
                c1.metric("총 계획 건수", f"{len(m_df)}건")
                c2.metric("병동 불일치", f"{len(m_df[m_df['검증결과']=='병동불일치'])}건")
                c3.metric("기록 누락", f"{len(m_df[m_df['검증결과']=='기록누락(P코드없음)'])}건")
                
                # 출력용 날짜 변환
                m_df['날짜'] = m_df['날짜'].dt.strftime('%Y-%m-%d')
                
                # 조건부 스타일링 (불일치 항목 강조)
                def style_rows(val):
                    if val == '병동불일치': return 'color: red; font-weight: bold'
                    if val == '기록누락(P코드없음)': return 'color: orange'
                    return ''

                st.dataframe(
                    m_df.style.applymap(style_rows, subset=['검증결과']),
                    use_container_width=True,
                    height=500
                )
                
                # 결과 다운로드
                csv = m_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(f"📥 {m}월 검증 결과 다운로드", csv, f"prime_result_{m}월.csv", "text/csv")
    else:
        st.info("2단계에서 '분석 실행' 버튼을 눌러주세요.")
