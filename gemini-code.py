import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. 유틸리티 함수: 날짜 및 데이터 정제 ---

def expand_date_range_with_month(date_str, year=2026):
    """'3/30~4/10' 문자열을 날짜 리스트로 변환 (시작일 기준 월 지정)"""
    try:
        # 불필요한 글자 제거 및 표준화
        date_str = str(date_str).replace('일', '').replace('평일', '').strip()
        if '~' not in date_str: return [], None
        
        parts = date_str.split('~')
        start_part = parts[0].strip()
        end_part = parts[1].strip()
        
        # 시작 날짜 파싱
        s_match = re.findall(r'\d+', start_part)
        s_month, s_day = int(s_match[0]), int(s_match[1])
        start_date = datetime(year, s_month, s_day)
        
        display_month = f"{year}년 {s_month}월"
        
        # 종료 날짜 파싱
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

def get_clean_df(uploaded_file):
    """파일 형식(CSV/Excel)에 상관없이 시트별 딕셔너리로 반환"""
    try:
        if uploaded_file.name.endswith('.csv'):
            return {"Sheet1": pd.read_csv(uploaded_file)}
        return pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    except Exception as e:
        st.error(f"파일 읽기 오류: {e}")
        return {}

# --- 2. 데이터 통합 엔진 ---

def get_dashboard_data(uploaded_p, uploaded_a):
    # 1. 계획표(Plan) 정제
    all_p_sheets = get_clean_df(uploaded_p)
    plan_data = []
    
    for _, df in all_p_sheets.items():
        if df.empty: continue
        
        # '근무조'와 '날짜구간(~)'이 있는 열 위치 찾기 (Header 자동 감지)
        date_cols, shift_col_idx = [], -1
        for i in range(min(10, len(df))): # 상위 10줄 스캔
            row_vals = df.iloc[i].astype(str).tolist()
            for j, val in enumerate(row_vals):
                if '~' in val and (j not in date_cols): date_cols.append(j)
                if '근무조' in val: shift_col_idx = j
            if date_cols and shift_col_idx != -1: break
        
        # 컬럼 이름 자체에서도 찾기
        for j, col in enumerate(df.columns):
            if '~' in str(col) and (j not in date_cols): date_cols.append(j)
            if '근무조' in str(col): shift_col_idx = j
        
        if shift_col_idx == -1: shift_col_idx = 1 # 기본값

        current_shift = "D"
        for idx, row in df.iterrows():
            shift_val = str(row.iloc[shift_col_idx])
            if 'D' in shift_val: current_shift = "D"
            elif 'E' in shift_val: current_shift = "E"
            
            for col_idx in date_cols:
                cell = str(row.iloc[col_idx])
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell)
                if match:
                    ward, name = match.group(1), match.group(2)
                    # 날짜 텍스트 추출 (제목줄 또는 셀 내용에서)
                    date_text = str(df.columns[col_idx]) if '~' in str(df.columns[col_idx]) else ""
                    # 제목줄에 없으면 위쪽 행에서 탐색
                    if not date_text or '~' not in date_text:
                        for k in range(idx, -1, -1):
                            if '~' in str(df.iloc[k, col_idx]):
                                date_text = str(df.iloc[k, col_idx]); break
                    
                    dates, target_month = expand_date_range_with_month(date_text)
                    for d in dates:
                        plan_data.append({'성함': name, '날짜': d, '계획병동': str(int(ward)), '근무조': current_shift, '분석월': target_month})
    
    # 2. 실제 근무표(Actual) 정제
    all_a_sheets = get_clean_df(uploaded_a)
    actual_data = []
    for sheet_name, df in all_a_sheets.items():
        if df.empty: continue
        # 시트명에서 월 추출
        m_match = re.findall(r'\d+', sheet_name)
        month = int(m_match[0]) if m_match else 3
        
        # '명' 컬럼과 '일' 컬럼 찾기
        name_idx, day_cols = -1, []
        for i in range(min(5, len(df))):
            row_vals = df.iloc[i].astype(str).tolist()
            if '명' in row_vals: name_idx = row_vals.index('명'); break
        if name_idx == -1:
            for j, col in enumerate(df.columns):
                if '명' in str(col): name_idx = j; break
        
        day_cols = [j for j, col in enumerate(df.columns) if '일' in str(col)]
        
        for idx, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if not name or name in ['nan', '명', '성명']: continue
            for d_idx in day_cols:
                day_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not day_match: continue
                day = int(day_match[0])
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        actual_data.append({'성함': name, '날짜': datetime(2026, month, day), '실제병동': str(int(ward_match.group(1)))})

    # 3. 통합 및 형평성 분석
    df_p, df_a = pd.DataFrame(plan_data), pd.DataFrame(actual_data)
    if df_p.empty or df_a.empty: return pd.DataFrame()

    df_p['날짜'] = pd.to_datetime(df_p['날짜'])
    df_a['날짜'] = pd.to_datetime(df_a['날짜'])
    
    merged = pd.merge(df_a, df_p, on=['성함', '날짜'], how='left').dropna(subset=['분석월'])
    merged['상태'] = merged.apply(lambda r: "지원(순환)" if r['실제병동'] == r['계획병동'] else "결원대체", axis=1)
    return merged

# --- 3. Streamlit UI ---

st.set_page_config(page_title="프라임 스마트 대시보드", layout="wide")
st.title("📊 프라임 간호사 통합 운영 대시보드")

c1, c2 = st.columns(2)
with c1: up_p = st.file_uploader("1. 계획표 업로드", type=["xlsx", "csv"])
with c2: up_a = st.file_uploader("2. 실제 근무표 업로드", type=["xlsx", "csv"])

if up_p and up_a:
    try:
        data = get_dashboard_data(up_p, up_a)
        if data.empty:
            st.warning("분석할 데이터가 없습니다. 파일의 날짜와 이름을 확인해주세요.")
        else:
            months = sorted(data['분석월'].unique())
            tabs = st.tabs(months)
            for i, month_tab in enumerate(tabs):
                with month_tab:
                    m_data = data[data['분석월'] == months[i]]
                    st.subheader(f"⚖️ {months[i]} 배정 형평성 리포트")
                    
                    final_summary = []
                    for name, group in m_data.groupby('성함'):
                        subs = group[group['상태'] == '결원대체']
                        # [보호막] 날짜가 유효한 경우에만 strftime 실행
                        sub_info = [f"{r['실제병동']}({r['날짜'].strftime('%m/%d') if pd.notnull(r['날짜']) else '날짜미상'})" for _, r in subs.iterrows()]
                        
                        final_summary.append({
                            '성함': name,
                            '결원대체 횟수': len(subs),
                            '지원(순환) 횟수': (group['상태'] == '지원(순환)').sum(),
                            '결원대체 병동 (날짜)': ", ".join(sub_info),
                            '지원 병동 이력': ", ".join(sorted(set(group[group['상태'] == '지원(순환)']['실제병동'])))
                        })
                    
                    st.table(pd.DataFrame(final_summary).sort_values(by='결원대체 횟수'))
                    
                    with st.expander("🔍 상세 내역"):
                        display_df = m_data.copy()
                        display_df['날짜'] = display_df['날짜'].dt.strftime('%Y-%m-%d')
                        st.dataframe(display_df[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']])
    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
