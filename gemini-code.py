import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. 유틸리티 함수: 날짜 처리 ---
def expand_date_range_with_month(date_str, year=2026):
    try:
        date_str = str(date_str).replace('일', '').replace('평일', '').strip()
        if '~' not in date_str: return [], None
        start_part, end_part = date_str.split('~')
        s_match = re.findall(r'\d+', start_part)
        s_month, s_day = int(s_match[0]), int(s_match[1])
        start_date = datetime(year, s_month, s_day)
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

def load_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return {"Sheet1": pd.read_csv(uploaded_file)}
    else:
        return pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')

# --- 2. 데이터 통합 분석 엔진 ---
def get_dashboard_data(uploaded_p, uploaded_a):
    all_p_data = load_file(uploaded_p)
    plan_records = []
    for sheet_name, df in all_p_data.items():
        if df.empty: continue
        date_cols = [i for i, col in enumerate(df.columns) if '~' in str(col)]
        if not date_cols:
            for i in range(min(5, len(df))):
                row_vals = df.iloc[i].astype(str).tolist()
                date_cols = [j for j, val in enumerate(row_vals) if '~' in val]
                if date_cols: break
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
                    date_text = str(df.columns[col_idx]) if '~' in str(df.columns[col_idx]) else cell
                    dates, target_month = expand_date_range_with_month(date_text)
                    if target_month:
                        for d in dates:
                            plan_records.append({'성함': name, '날짜': d, '계획병동': str(int(ward)), '근무조': curr_shift, '분석월': target_month})
    df_p = pd.DataFrame(plan_records)

    all_a_data = load_file(uploaded_a)
    actual_records = []
    for sheet_name, df in all_a_data.items():
        if df.empty: continue
        month = 3
        m_match = re.findall(r'\d+', str(sheet_name))
        if m_match: month = int(m_match[0])
        name_col_idx = -1
        for i, col in enumerate(df.columns):
            if '명' in str(col): name_col_idx = i; break
        if name_col_idx == -1: name_col_idx = 2
        day_cols = [i for i, col in enumerate(df.columns) if '일' in str(col)]
        for idx, row in df.iterrows():
            name = str(row.iloc[name_col_idx]).strip()
            if not name or name in ['nan', '명', '성명']: continue
            row_str = " ".join(row.astype(str))
            row_m_match = re.findall(r'(\d+)월', row_str)
            if row_m_match: month = int(row_m_match[0])
            for d_idx in day_cols:
                day_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not day_match: continue
                day = int(day_match[0])
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        actual_records.append({'성함': name, '날짜': datetime(2026, month, day), '실제병동': str(int(ward_match.group(1)))})
    df_a = pd.DataFrame(actual_records)
    if df_p.empty or df_a.empty: return pd.DataFrame()

    df_p['날짜'] = pd.to_datetime(df_p['날짜'])
    df_a['날짜'] = pd.to_datetime(df_a['날짜'])
    merged = pd.merge(df_a, df_p, on=['성함', '날짜'], how='left')
    merged = merged.dropna(subset=['분석월'])
    merged['상태'] = merged.apply(lambda r: "지원(순환)" if r['실제병동'] == r['계획병동'] else "결원대체", axis=1)
    return merged

# --- 3. Streamlit 대시보드 화면 ---
st.set_page_config(page_title="프라임 스마트 대시보드", layout="wide")
st.title("🏥 프라임 간호사 통합 운영 대시보드")

c1, c2 = st.columns(2)
with c1: up_p = st.file_uploader("1. 계획표 업로드 (Excel/CSV)", type=["xlsx", "csv"])
with c2: up_a = st.file_uploader("2. 실제 근무표 업로드 (Excel/CSV)", type=["xlsx", "csv"])

if up_p and up_a:
    try:
        with st.spinner('데이터 분석 중...'):
            data = get_dashboard_data(up_p, up_a)
        if data.empty:
            st.warning("⚠️ 분석할 수 있는 데이터가 없습니다. 파일 내용을 확인해주세요.")
        else:
            months = sorted(data['분석월'].unique())
            tabs = st.tabs(months)
            for i, month_tab in enumerate(tabs):
                with month_tab:
                    m_data = data[data['분석월'] == months[i]]
                    st.subheader(f"⚖️ {months[i]} 배정 형평성 분석")
                    
                    # pd.notna()로 날짜가 진짜 있을 때만 strftime을 하도록 수정했습니다!
                    summary = m_data.groupby('성함').apply(lambda x: pd.Series({
                        '결원대체 횟수': (x['상태'] == '결원대체').sum(),
                        '지원(순환) 횟수': (x['상태'] == '지원(순환)').sum(),
                        '결원대체 병동 (날짜)': ", ".join([f"{row['실제병동']}({row['날짜'].strftime('%m/%d') if pd.notna(row['날짜']) else '미상'})" for _, row in x[x['상태'] == '결원대체'].iterrows()]),
                        '지원 병동 이력': ", ".join(sorted(set(x[x['상태'] == '지원(순환)']['실제병동'])))
                    })).reset_index()
                    st.table(summary.sort_values(by='결원대체 횟수'))
                    
                    with st.expander("🔍 상세 내역 확인"):
                        temp_df = m_data.copy()
                        # 상세 내역 출력 전에도 날짜가 있는지 체크합니다.
                        if '날짜' in temp_df.columns:
                            temp_df['날짜'] = pd.to_datetime(temp_df['날짜']).dt.strftime('%Y-%m-%d')
                        st.dataframe(temp_df[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']])
    except Exception as e:
        st.error(f"❌ 분석 중 에러 발생: {e}")
