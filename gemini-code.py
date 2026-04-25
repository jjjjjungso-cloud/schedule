import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

def expand_dates(date_text, year=2026):
    """'3/3~3/13' 형태의 텍스트를 개별 날짜 리스트로 변환"""
    try:
        clean_text = re.sub(r'[^0-9~]', '', str(date_text))
        if '~' not in clean_text: return []
        parts = clean_text.split('~')
        s_m, s_d = map(int, re.findall(r'\d+', parts[0]))
        s_date = datetime(year, s_m, s_d)
        
        e_nums = re.findall(r'\d+', parts[1])
        e_m = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_d = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        e_date = datetime(year, e_m, e_d)
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except: return []

def extract_prime_logic(uploaded_file, year):
    # 헤더 없이 모든 칸을 읽어오기 (디버깅 화면과 동일한 구조)
    df = pd.read_excel(uploaded_file, header=None, engine='openpyxl')
    
    # 1. 날짜 열(Index)과 근무조 열(Index) 찾기
    date_cols = []
    shift_col_idx = -1
    
    # 상단 10줄을 뒤져서 구조 파악
    for r in range(min(10, len(df))):
        row_vals = df.iloc[r].astype(str).tolist()
        for c, val in enumerate(row_vals):
            if '~' in val: date_cols.append(c)
            if '근무조' in val: shift_col_idx = c
            
    if shift_col_idx == -1: shift_col_idx = 2 # 스크린샷 기준 2번 열
    
    results = []
    current_shift = "D" # 기본값
    
    # 2. 데이터 추출 (행 단위로 순회)
    for r in range(len(df)):
        # [세로축 로직] 근무조 열 확인 (D/E가 보이면 업데이트, None이면 유지)
        shift_cell = str(df.iloc[r, shift_col_idx]).strip()
        if shift_cell == 'D': current_shift = 'D'
        elif shift_cell == 'E': current_shift = 'E'
        # None일 때는 이전 current_shift를 그대로 사용함 (소영님 로직)

        # [가로축 로직] 날짜 열들을 순회
        for c in date_cols:
            cell_val = str(df.iloc[r, c])
            # '72 박소영' 패턴 찾기
            match = re.search(r'(\d+)\s+([가-힣]{2,4})', cell_val)
            
            if match:
                ward = match.group(1)
                name = match.group(2)
                
                # 날짜 헤더(보통 3~4번 행에 있음) 찾기
                date_header = ""
                for head_r in range(r):
                    head_val = str(df.iloc[head_r, c])
                    if '~' in head_val:
                        date_header = head_val
                        break
                
                dates = expand_dates(date_header, year)
                for d in dates:
                    results.append({
                        '날짜': d.strftime('%Y-%m-%d'),
                        '성함': name,
                        '계획병동': ward,
                        '근무조': current_shift
                    })
                    
    return pd.DataFrame(results).drop_duplicates()

# --- Streamlit 실행 부분 ---
st.title("🏥 프라임 간호사 배정표 지능형 추출기")
selected_year = st.sidebar.selectbox("연도 설정", [2026, 2027])
up_file = st.file_uploader("배정표 엑셀 업로드", type="xlsx")

if up_file:
    df_result = extract_prime_logic(up_file, selected_year)
    if not df_result.empty:
        st.success("✅ 소영님의 로직대로 데이터를 성공적으로 읽어왔습니다!")
        st.dataframe(df_result, use_container_width=True)
    else:
        st.warning("데이터를 찾지 못했습니다. 디버깅 화면의 구조와 파일이 일치하는지 확인해주세요.")
