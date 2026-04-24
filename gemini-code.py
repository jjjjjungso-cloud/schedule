import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. 유틸리티 및 정제 엔진 ---

def expand_date_range_with_month(date_str, year=2026):
    """구간을 개별 날짜로 풀고, 시작일의 월을 '분석월'로 반환"""
    try:
        date_str = date_str.replace('일', '').replace('평일', '').strip()
        start_part, end_part = date_str.split('~')
        s_match = re.findall(r'\d+', start_part)
        s_month, s_day = int(s_match[0]), int(s_match[1])
        start_date = datetime(year, s_month, s_day)
        
        # 분석월 설정 (소영님의 규칙: 시작일 기준)
        display_month = f"{year}년 {s_month}월"
        
        e_match = re.findall(r'\d+', end_part)
        if len(e_match) == 2:
            e_month, e_day = int(e_match[0]), int(e_match[1])
        else:
            e_month, e_day = s_month, int(e_match[0])
        end_date = datetime(year, e_month, e_day)
        
        dates = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        return dates, display_month
    except:
        return [], None

def get_dashboard_data(uploaded_p, uploaded_a):
    # 1. 계획표(Plan) 정제
    all_p_sheets = pd.read_excel(uploaded_p, sheet_name=None, engine='openpyxl')
    plan_data = []
    for sheet_name, df in all_p_sheets.items():
        date_cols = [i for i, col in enumerate(df.columns) if '~' in str(col)]
        shift_col = next((i for i, col in enumerate(df.columns) if '근무조' in str(col)), 1)
        for idx, row in df.iterrows():
            curr_shift = "D" if 'D' in str(row[shift_col]) else "E"
            for col_idx in date_cols:
                cell = str(row[col_idx])
                match = re.search(r'(\d+)\s*\n\s*([가-힣]+)', cell)
                if match:
                    ward, name = match.group(1), match.group(2)
                    dates, target_month = expand_date_range_with_month(df.columns[col_idx])
                    for d in dates:
                        plan_data.append({'성함': name, '날짜': d, '계획병동': str(int(ward)), '근무조': curr_shift, '분석월': target_month})
    df_p = pd.DataFrame(plan_data)

    # 2. 실제 근무표(Actual) 정제
    all_a_sheets = pd.read_excel(uploaded_a, sheet_name=None, engine='openpyxl')
    actual_data = []
    for sheet_name, df in all_a_sheets.items():
        m_match = re.findall(r'\d+', sheet_name)
        month = int(m_match[0]) if m_match else 3
        name_col = next((c for c in df.columns if '명' in str(c)), '명')
        day_cols = [c for c in df.columns if '일' in str(c)]
        for _, row in df.iterrows():
            name = row[name_col]
            if pd.isna(name): continue
            for d_col in day_cols:
                day = int(re.findall(r'\d+', d_col)[0])
                code = str(row[d_col])
                if code.startswith('P-'): # D4, D8 등 포함
                    w_match = re.search(r'/(\d+)', code)
                    if w_match:
                        actual_data.append({'성함': name, '날짜': datetime(2026, month, day), '실제병동': str(int(w_match.group(1)))})
    df_a = pd.DataFrame(actual_data)

    # 3. 데이터 통합 및 분석
    merged = pd.merge(df_a, df_p, on=['성함', '날짜'], how='left')
    merged = merged.dropna(subset=['분석월']) # 계획 구간에 없는 날짜 제외
    
    def classify(row):
        return "지원(순환)" if row['실제병동'] == row['계획병동'] else "결원대체"
    merged['상태'] = merged.apply(classify, axis=1)
    
    return merged

# --- 2. Streamlit 대시보드 화면 ---

st.set_page_config(page_title="프라임 스마트 대시보드", layout="wide")
st.title("📊 프라임 간호사 월별 운영 대시보드")

col1, col2 = st.columns(2)
with col1:
    up_p = st.file_uploader("1. 대기병동 배정표(Plan) 업로드", type="xlsx")
with col2:
    up_a = st.file_uploader("2. 실제 근무스케줄표(Actual) 업로드", type="xlsx")

if up_p and up_a:
    data = get_dashboard_data(up_p, up_a)
    months = sorted(data['분석월'].unique())
    
    # 월별 탭 생성
    tabs = st.tabs(months)
    
    for i, month_tab in enumerate(tabs):
        with month_tab:
            m_data = data[data['분석월'] == months[i]]
            
            # 1. 형평성 지표 (결원대체 적은 순)
            st.subheader(f"⚖️ {months[i]} 배정 형평성 순위")
            st.caption("결원대체 횟수가 적은 분이 상단에 노출됩니다. (차기 결원 발생 시 우선 추천)")
            
            summary = m_data.groupby('성함').apply(lambda x: pd.Series({
                '결원대체 횟수': (x['상태'] == '결원대체').sum(),
                '지원(순환) 횟수': (x['상태'] == '지원(순환)').sum(),
                '결원대체 병동': ", ".join(sorted(set(x[x['상태'] == '결원대체']['실제병동']))),
                '지원 병동(주차별)': ", ".join(sorted(set(x[x['상태'] == '지원(순환)']['실제병동'])))
            })).reset_index()
            
            summary = summary.sort_values(by='결원대체 횟수')
            st.table(summary)
            
            # 2. 상세 타임라인
            with st.expander(f"🔍 {months[i]} 상세 근무 매칭 내역 보기"):
                st.dataframe(m_data[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']].sort_values(['성함', '날짜']), use_container_width=True)

    # 전체 데이터 다운로드
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        data.to_excel(writer, index=False, sheet_name='통합분석결과')
    st.download_button("📥 전체 분석 데이터 다운로드", output.getvalue(), "NSS_Final_Dashboard.xlsx")
