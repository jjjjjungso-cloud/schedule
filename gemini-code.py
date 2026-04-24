import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 확장 함수: '3/30~4/10' -> [2026-03-30, 2026-03-31, ...] ---
def expand_date_range(date_str, year=2026):
    try:
        # 특수문자 제거 및 분리
        date_str = str(date_str).replace('일', '').replace('(평일)', '').strip()
        if '~' not in date_str: return []
        
        start_part, end_part = date_str.split('~')
        
        # 시작 날짜 추출
        s_nums = re.findall(r'\d+', start_part)
        s_month, s_day = int(s_nums[0]), int(s_nums[1])
        start_date = datetime(year, s_month, s_day)
        
        # 종료 날짜 추출
        e_nums = re.findall(r'\d+', end_part)
        if len(e_nums) == 2: # '4/10' 형태
            e_month, e_day = int(e_nums[0]), int(e_nums[1])
        else: # '24' 형태 (시작일과 같은 달)
            e_month, e_day = s_month, int(e_nums[0])
        end_date = datetime(year, e_month, e_day)
        
        return [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    except:
        return []

# --- 2. 대기배정표 정제 엔진 ---
def get_clean_plan_dashboard(uploaded_file):
    # 엑셀 파일 읽기
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    all_records = []

    for sheet_name, df in all_sheets.items():
        # [에러 방지] '근무조' 열 위치 자동 감지
        shift_col_idx = -1
        for i in range(min(10, len(df))): # 상위 10행 스캔
            row_vals = df.iloc[i].astype(str).tolist()
            for j, val in enumerate(row_vals):
                if '근무조' in val:
                    shift_col_idx = j
                    break
            if shift_col_idx != -1: break
        
        if shift_col_idx == -1: shift_col_idx = 1 # 못 찾으면 기본값 B열
        
        # [에러 방지] 날짜 구간(~)이 포함된 열 찾기
        date_cols = [j for j, col in enumerate(df.columns) if '~' in str(col)]
        
        current_shift = "D"
        for idx, row in df.iterrows():
            # 근무조 업데이트
            shift_val = str(row.iloc[shift_col_idx])
            if 'D' in shift_val: current_shift = "D"
            elif 'E' in shift_val: current_shift = "E"
            
            for col_idx in date_cols:
                cell_val = str(row.iloc[col_idx])
                # "병동\n이름" 추출 (예: 72\n박소영)
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell_val)
                
                if match:
                    ward, name = match.group(1), match.group(2)
                    # 해당 구간의 모든 날짜 생성
                    date_text = str(df.columns[col_idx])
                    dates = expand_date_range(date_text)
                    
                    if dates:
                        # 시작일 기준 분석월 설정 (예: 2026년 3월)
                        analysis_month = f"{dates[0].year}년 {dates[0].month}월"
                        for d in dates:
                            all_records.append({
                                "날짜": d.strftime('%Y-%m-%d'),
                                "분석월": analysis_month,
                                "근무조": current_shift,
                                "성함": name,
                                "계획병동": ward
                            })
    return pd.DataFrame(all_records)

# --- 3. 스트림릿 UI ---
st.set_page_config(page_title="프라임 배정 분석", layout="wide")
st.title("📊 프라임팀 대기배정표 상세 분석")

uploaded_file = st.file_uploader("프라임간호사 대기병동 배정 엑셀 파일을 업로드하세요.", type=['xlsx'])

if uploaded_file:
    with st.spinner('데이터를 쪼개는 중입니다...'):
        df_result = get_clean_plan_dashboard(uploaded_file)
    
    if not df_result.empty:
        # 월별 탭 생성
        months = sorted(df_result['분석월'].unique())
        tabs = st.tabs(months)
        
        for i, tab in enumerate(tabs):
            with tab:
                m_data = df_result[df_result['분석월'] == months[i]].sort_values('날짜')
                
                # 요약 지표
                c1, c2, c3 = st.columns(3)
                c1.metric("총 인원", f"{m_data['성함'].nunique()}명")
                c2.metric("총 계획 건수", f"{len(m_data)}건")
                c3.metric("최다 배정 병동", m_data['계획병동'].mode()[0])
                
                # 데이터 테이블
                st.write(f"#### 📅 {months[i]} 일별 배정 현황")
                st.dataframe(m_data[['날짜', '근무조', '성함', '계획병동']], use_container_width=True)
                
                # 병동별 배정 통계
                st.write("#### 🏥 병동별 배정 빈도")
                st.bar_chart(m_data['계획병동'].value_counts())
    else:
        st.error("데이터를 찾을 수 없습니다. 파일의 '근무조'와 날짜(~) 형식을 확인해주세요.")
