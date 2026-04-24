import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 확장 로직 (3/30~4/10 -> 개별 날짜 리스트) ---
def expand_date_range(date_str, year=2026):
    try:
        # 표준화 및 분리
        date_str = str(date_str).replace('일', '').replace('(평일)', '').strip()
        if '~' not in date_str: return []
        
        start_part, end_part = date_str.split('~')
        
        # 시작 날짜 (월/일)
        s_nums = re.findall(r'\d+', start_part)
        s_month, s_day = int(s_nums[0]), int(s_nums[1])
        start_date = datetime(year, s_month, s_day)
        
        # 종료 날짜
        e_nums = re.findall(r'\d+', end_part)
        if len(e_nums) == 2:
            e_month, e_day = int(e_nums[0]), int(e_nums[1])
        else:
            e_month, e_day = s_month, int(e_nums[0])
        end_date = datetime(year, e_month, e_day)
        
        return [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    except:
        return []

# --- 2. 대기배정표 정제 엔진 ---
def get_daily_assignment_df(uploaded_file):
    # Excel/CSV 자동 대응
    try:
        if uploaded_file.name.endswith('.csv'):
            all_sheets = {"Sheet1": pd.read_csv(uploaded_file)}
        else:
            all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    except:
        return pd.DataFrame()

    daily_records = []

    for sheet_name, df in all_sheets.items():
        # 데이터 헤더 및 열 자동 감지
        date_cols = [i for i, col in enumerate(df.columns) if '~' in str(col)]
        shift_col_idx = next((i for i, col in enumerate(df.columns) if '근무조' in str(col)), 1)
        
        current_shift = "D"
        for idx, row in df.iterrows():
            shift_val = str(row.iloc[shift_col_idx])
            if 'D' in shift_val: current_shift = "D"
            elif 'E' in shift_val: current_shift = "E"
            
            for col_idx in date_cols:
                cell_val = str(row.iloc[col_idx])
                # "병동\n이름" 추출
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell_val)
                if match:
                    ward, name = match.group(1), match.group(2)
                    date_text = str(df.columns[col_idx])
                    dates = expand_date_range(date_text)
                    
                    if dates:
                        # 소영님 규칙: 구간의 시작일 기준 월 저장
                        target_month = f"{dates[0].year}년 {dates[0].month}월"
                        for d in dates:
                            daily_records.append({
                                "날짜": d.strftime('%Y-%m-%d'),
                                "요일": d.strftime('%a'),
                                "분석기준월": target_month,
                                "근무조": current_shift,
                                "성함": name,
                                "계획병동": ward
                            })
    return pd.DataFrame(daily_records)

# --- 3. Streamlit 대시보드 UI ---
st.set_page_config(page_title="프라임 배정 분석", layout="wide")
st.title("🏥 프라임팀 대기배정표 분석 대시보드")

uploaded_file = st.file_uploader("프라임팀 대기배정표 파일을 업로드하세요 (Excel/CSV)", type=['xlsx', 'csv'])

if uploaded_file:
    df_final = get_daily_assignment_df(uploaded_file)
    
    if not df_final.empty:
        # 월별 탭 생성
        months = sorted(df_final['분석기준월'].unique())
        tabs = st.tabs(months)
        
        for i, tab in enumerate(tabs):
            with tab:
                m_data = df_final[df_final['분석기준월'] == months[i]]
                
                col1, col2 = st.columns(2)
                col1.metric("배정 인원", f"{m_data['성함'].nunique()}명")
                col2.metric("총 배정 일수", f"{len(m_data)}일")
                
                st.subheader(f"📅 {months[i]} 일별 상세 계획")
                st.dataframe(m_data[['날짜', '요일', '근무조', '성함', '계획병동']].sort_values('날짜'), use_container_width=True)
                
                st.subheader("📊 병동별 지원 빈도")
                st.bar_chart(m_data['계획병동'].value_counts())
    else:
        st.error("데이터를 읽어오지 못했습니다. 파일 내 날짜(~ 포함)와 근무조 열을 확인해주세요.")
