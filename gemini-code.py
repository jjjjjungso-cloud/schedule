import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. 유틸리티 및 정제 엔진 ---

def expand_date_range_with_month(date_str, year=2026):
    """'3/30~4/10' 문자열을 날짜 리스트로 풀고, 시작일 기준의 '분석월' 반환"""
    try:
        date_str = str(date_str).replace('일', '').replace('평일', '').strip()
        if '~' not in date_str: return [], None
        
        start_part, end_part = date_str.split('~')
        s_match = re.findall(r'\d+', start_part)
        s_month, s_day = int(s_match[0]), int(s_match[1])
        start_date = datetime(year, s_month, s_day)
        
        # 소영님 규칙: 구간의 시작일이 속한 월을 '분석월'로 지정
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
    """계획표와 실제근무표를 읽어 통합 분석 데이터 생성"""
    
    # 1. 계획표(Plan) 정제
    all_p_sheets = pd.read_excel(uploaded_p, sheet_name=None, engine='openpyxl')
    plan_data = []
    
    for sheet_name, df in all_p_sheets.items():
        date_cols = [i for i, col in enumerate(df.columns) if '~' in str(col)]
        shift_col_idx = -1
        for i, col in enumerate(df.columns):
            if '근무조' in str(col): shift_col_idx = i; break
        if shift_col_idx == -1:
            for i in range(min(5, len(df))):
                row_vals = df.iloc[i].astype(str).tolist()
                for j, val in enumerate(row_vals):
                    if '근무조' in val: shift_col_idx = j; break
                if shift_col_idx != -1: break
        if shift_col_idx == -1: shift_col_idx = 1
        
        for idx, row in df.iterrows():
            shift_val = str(row.iloc[shift_col_idx])
            if 'D' in shift_val: curr_shift = "D"
            elif 'E' in shift_val: curr_shift = "E"
            else: continue
            
            for col_idx in date_cols:
                cell = str(row.iloc[col_idx])
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell)
                if match:
                    ward, name = match.group(1), match.group(2)
                    dates, target_month = expand_date_range_with_month(df.columns[col_idx])
                    if target_month:
                        for d in dates:
                            plan_data.append({'성함': name, '날짜': d, '계획병동': str(int(ward)), '근무조': curr_shift, '분석월': target_month})
    
    df_p = pd.DataFrame(plan_data)
    if not df_p.empty:
        df_p['날짜'] = pd.to_datetime(df_p['날짜'], errors='coerce')

    # 2. 실제 근무표(Actual) 정제
    all_a_sheets = pd.read_excel(uploaded_a, sheet_name=None, engine='openpyxl')
    actual_data = []
    for sheet_name, df in all_a_sheets.items():
        m_match = re.findall(r'\d+', sheet_name)
        month = int(m_match[0]) if m_match else 3
        name_col_idx = -1
        for i, col in enumerate(df.columns):
            if '명' in str(col): name_col_idx = i; break
        if name_col_idx == -1:
            row0 = df.iloc[0].astype(str).tolist()
            for j, val in enumerate(row0):
                if '명' in val: name_col_idx = j; break
        day_cols = [i for i, col in enumerate(df.columns) if '일' in str(col)]
        
        for idx, row in df.iterrows():
            name = str(row.iloc[name_col_idx]).strip()
            if not name or name == 'nan' or name == '명': continue
            for d_idx in day_cols:
                day_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not day_match: continue
                day = int(day_match[0])
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        actual_data.append({'성함': name, '날짜': datetime(2026, month, day), '실제병동': str(int(ward_match.group(1)))})
    
    df_a = pd.DataFrame(actual_data)
    if not df_a.empty:
        df_a['날짜'] = pd.to_datetime(df_a['날짜'], errors='coerce')

    if df_p.empty or df_a.empty:
        return pd.DataFrame()

    merged = pd.merge(df_a, df_p, on=['성함', '날짜'], how='left')
    merged = merged.dropna(subset=['분석월'])
    merged['상태'] = merged.apply(lambda r: "지원(순환)" if r['실제병동'] == r['계획병동'] else "결원대체", axis=1)
    return merged

# --- 2. Streamlit 대시보드 UI ---

st.set_page_config(page_title="프라임 스마트 대시보드", layout="wide")
st.title("🏥 프라임 간호사 통합 운영 대시보드")

col1, col2 = st.columns(2)
with col1: up_p = st.file_uploader("1. 계획표 업로드", type="xlsx")
with col2: up_a = st.file_uploader("2. 실제 근무표 업로드", type="xlsx")

if up_p and up_a:
    try:
        data = get_dashboard_data(up_p, up_a)
        
        if data.empty:
            st.warning("데이터 매칭 결과가 없습니다. 파일의 날짜와 시트명을 확인해 주세요.")
        else:
            months = sorted(data['분석월'].unique())
            tabs = st.tabs(months)
            
            for i, month_tab in enumerate(tabs):
                with month_tab:
                    m_data = data[data['분석월'] == months[i]]
                    st.subheader(f"⚖️ {months[i]} 배정 형평성 리포트")
                    
                    # [수정된 부분] 날짜 변환 시 에러 방지 처리 추가
                    summary = m_data.groupby('성함').apply(lambda x: pd.Series({
                        '결원대체 횟수': (x['상태'] == '결원대체').sum(),
                        '지원(순환) 횟수': (x['상태'] == '지원(순환)').sum(),
                        '결원대체 병동 (날짜)': ", ".join([f"{row['실제병동']}({row['날짜'].strftime('%m/%d') if pd.notna(row['날짜']) and hasattr(row['날짜'], 'strftime') else '날짜미상'})" 
                                                   for _, row in x[x['상태'] == '결원대체'].iterrows()]),
                        '지원 병동 이력': ", ".join(sorted(set(x[x['상태'] == '지원(순환)']['실제병동'])))
                    })).reset_index()
                    
                    summary = summary.sort_values(by=['결원대체 횟수', '지원(순환) 횟수'])
                    st.table(summary)
                    
                    with st.expander("🔍 일자별 상세 내역 확인"):
                        display_df = m_data[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']].copy()
                        # 날짜 표시 형식 변환 시에도 안전장치 추가
                        display_df['날짜'] = pd.to_datetime(display_df['날짜']).dt.strftime('%Y-%m-%d')
                        st.dataframe(display_df.sort_values(['성함', '날짜']), use_container_width=True)

    except Exception as e:
        st.error(f"데이터 처리 중 오류 발생: {e}")
