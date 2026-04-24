import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 확장 로직 (3/30~4/10 -> 개별 날짜) ---
def expand_dates(date_text, year=2026):
    if pd.isna(date_text): return []
    try:
        clean_str = re.sub(r'[^0-9~]', '', str(date_text))
        if '~' not in clean_str: return []
        parts = clean_str.split('~')
        s_m, s_d = map(int, re.findall(r'\d+', parts[0]))
        s_date = datetime(year, s_m, s_d)
        e_nums = re.findall(r'\d+', parts[1])
        e_m = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_d = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        return [s_date + timedelta(days=x) for x in range((datetime(year, e_m, e_d) - s_date).days + 1)]
    except: return []

# --- 2. 배정표(Plan) 무시하며 추출하기 ---
def extract_plan(uploaded_file, year, exclude_names):
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    results = []
    for _, df in all_sheets.items():
        # 열 위치 찾기 (날짜랑 근무조만 찾으면 끝)
        shift_idx = -1
        date_cols = []
        for i in range(min(15, len(df))):
            row = df.iloc[i].astype(str).tolist() # 일단 찾을 때만 잠깐 글자로
            for j, val in enumerate(row):
                if '근무조' in val: shift_idx = j
                if '~' in val: date_cols.append(j)
        
        if shift_idx == -1: shift_idx = 1
        
        curr_shift = "D"
        for _, row in df.iterrows():
            # 근무조 확인
            s_val = str(row.iloc[shift_idx]).upper()
            if 'D' in s_val: curr_shift = "D"
            elif 'E' in s_val: curr_shift = "E"
            
            for c_idx in date_cols:
                cell = row.iloc[c_idx]
                # [가장 중요한 부분] 우리가 원하는 패턴 아니면 그냥 무시!
                try:
                    match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]{2,4})', str(cell))
                    if match:
                        ward, name = match.group(1), match.group(2)
                        if name in exclude_names: continue
                        dates = expand_dates(df.columns[c_idx], year)
                        for d in dates:
                            results.append({'날짜': d.strftime('%Y-%m-%d'), '성함': name, '계획병동': ward, '근무조': curr_shift})
                except:
                    continue # 에러 나면 그냥 다음 칸으로 (무시)
    return pd.DataFrame(results).drop_duplicates()

# --- 3. UI 구성 (에러 났던 부분 수정) ---
st.set_page_config(page_title="프라임 매니저", layout="wide")
st.title("🏥 프라임 간호사 스마트 배치 시스템 (최종)")

year = st.sidebar.selectbox("연도", [2026, 2027])
exclude_names = ['고정민']

up_p = st.file_uploader("계획표(Plan) 파일을 올려주세요", type="xlsx")

if up_p:
    # 에러 났던 st.write와 st.dataframe 구조를 분리해서 깔끔하게 수정
    st.markdown("### ✅ 계획표 정제 결과")
    df_plan = extract_plan(up_p, year, exclude_names)
    
    if not df_plan.empty:
        st.dataframe(df_plan, use_container_width=True)
        st.success(f"총 {len(df_plan)}개의 데이터를 찾았습니다.")
    else:
        st.warning("데이터를 찾지 못했습니다. 파일의 형식을 확인해 주세요.")
