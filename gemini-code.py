import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 구간 확장 (4/13~24 -> 13일부터 24일까지 생성) ---
def expand_date_range(date_text, year=2026):
    if pd.isna(date_text): return []
    try:
        clean_text = re.sub(r'[^0-9~]', '', str(date_text))
        if '~' not in clean_text: return []
        
        parts = clean_text.split('~')
        start_nums = re.findall(r'\d+', parts[0])
        if len(start_nums) < 2: return []
        s_date = datetime(year, int(start_nums[0]), int(start_nums[1]))
        
        end_nums = re.findall(r'\d+', parts[1])
        if not end_nums: return []
        # '24'만 있을 경우 시작 월(4월)을 그대로 사용
        e_m = int(end_nums[0]) if len(end_nums) == 2 else s_date.month
        e_d = int(end_nums[1]) if len(end_nums) == 2 else int(end_nums[0])
        e_date = datetime(year, e_m, e_d)
        
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except: return []

# --- 2. 한 칸에 여러 명 있는 데이터를 모두 찾는 로직 ---
def robust_extract_plan(uploaded_file, year):
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None)
    results = []
    exclude_names = ['고정민']

    for _, df in all_sheets.items():
        if df.shape[0] < 5: continue
        
        # 날짜 기둥(열)과 근무조 기둥 위치 파악
        date_col_map = {}
        shift_col_idx = 1
        
        for r_idx in range(min(20, len(df))):
            for c_idx in range(len(df.columns)):
                cell_val = str(df.iloc[r_idx, c_idx])
                if '~' in cell_val:
                    dates = expand_date_range(cell_val, year)
                    if dates: date_col_map[c_idx] = dates
                if '근무조' in cell_val: shift_col_idx = c_idx

        # 데이터 추출 시작
        last_shift = "D"
        for r_idx in range(len(df)):
            # 근무조 열에서 D/E 파악 (병합된 셀 대응)
            row_shift_val = str(df.iloc[r_idx, shift_col_idx]).upper()
            if 'D' in row_shift_val: last_shift = "D"
            elif 'E' in row_shift_val: last_shift = "E"
            
            for c_idx, date_list in date_col_map.items():
                cell_content = str(df.iloc[r_idx, c_idx])
                
                # [핵심 변경] re.search 대신 re.finditer를 사용하여 한 칸 안의 모든 [숫자+이름] 매칭
                # 51 정윤정, 72 기아현 등 모든 세트를 찾아냄
                matches = re.finditer(r'(\d+)\s+([가-힣]{2,4})', cell_content)
                
                found_any = False
                for match in matches:
                    ward = match.group(1)
                    name = match.group(2)
                    if name in exclude_names: continue
                    
                    found_any = True
                    for d in date_list:
                        results.append({
                            '날짜': d.strftime('%Y-%m-%d'),
                            '근무조': last_shift,
                            '성함': name,
                            '계획병동': ward
                        })
                
                # 위 패턴으로 안 잡힐 경우(줄바꿈이 특수한 경우) 대비 보조 매칭
                if not found_any:
                    alt_matches = re.finditer(r'(\d+)\s*[\n\r]+\s*([가-힣]{2,4})', cell_content)
                    for match in alt_matches:
                        ward = match.group(1)
                        name = match.group(2)
                        if name in exclude_names: continue
                        for d in date_list:
                            results.append({
                                '날짜': d.strftime('%Y-%m-%d'),
                                '근무조': last_shift,
                                '성함': name,
                                '계획병동': ward
                            })
                        
    return pd.DataFrame(results).drop_duplicates()

# --- 3. UI 구성 ---
st.set_page_config(page_title="프라임 배정표 마스터", layout="wide")
st.title("🏥 프라임 배정표 멀티 추출기")

up_p = st.file_uploader("배정표 엑셀 파일을 올려주세요", type="xlsx")
selected_year = st.sidebar.selectbox("연도 설정", [2026, 2027])

if up_p:
    with st.spinner('한 칸에 있는 모든 인원을 분리하여 분석 중입니다...'):
        df_plan = robust_extract_plan(up_p, selected_year)
        
        if not df_plan.empty:
            st.success(f"✅ 총 {len(df_plan)}개의 배정 이력을 찾아냈습니다!")
            # 보기 편하게 날짜와 성함순으로 정렬
            df_plan = df_plan.sort_values(by=['날짜', '성함'])
            st.dataframe(df_plan, use_container_width=True)
        else:
            st.warning("데이터를 찾지 못했습니다. 파일 내용을 확인해주세요.")
