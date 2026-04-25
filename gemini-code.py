import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 구간을 개별 날짜로 변환 ---
def expand_date_range(date_text, year=2026):
    if pd.isna(date_text): return []
    try:
        # 숫자와 ~ 기호만 남기기
        clean_text = re.sub(r'[^0-9~]', '', str(date_text))
        if '~' not in clean_text: return []
        
        parts = clean_text.split('~')
        start_nums = re.findall(r'\d+', parts[0])
        if len(start_nums) < 2: return []
        start_date = datetime(year, int(start_nums[0]), int(start_nums[1]))
        
        end_nums = re.findall(r'\d+', parts[1])
        if not end_nums: return []
        end_m = int(end_nums[0]) if len(end_nums) == 2 else start_date.month
        end_d = int(end_nums[1]) if len(end_nums) == 2 else int(end_nums[0])
        end_date = datetime(year, end_m, end_d)
        
        return [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    except: return []

# --- 2. 시트 전체를 뒤져서 매칭하는 로직 ---
def robust_extract_plan(uploaded_file, year):
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None) # 헤더 없이 전체 읽기
    results = []
    exclude_names = ['고정민']

    for _, df in all_sheets.items():
        # 데이터가 너무 적은 시트는 무시
        if df.shape[0] < 5: continue
        
        # [Step A] 날짜가 적힌 열과 근무조가 적힌 열 위치 찾기
        date_col_map = {} # {열번호: [날짜리스트]}
        shift_col_idx = 1 # 기본값
        
        # 상위 20줄을 뒤져서 날짜 구간(~ 포함)이 있는 칸을 모두 찾음
        for r_idx in range(min(20, len(df))):
            for c_idx in range(len(df.columns)):
                cell_val = str(df.iloc[r_idx, c_idx])
                if '~' in cell_val:
                    dates = expand_date_range(cell_val, year)
                    if dates:
                        date_col_map[c_idx] = dates
                if '근무조' in cell_val:
                    shift_col_idx = c_idx

        # [Step B] 본격적으로 행을 돌며 데이터 추출
        last_shift = "D"
        for r_idx in range(len(df)):
            # 근무조 파악
            row_shift_val = str(df.iloc[r_idx, shift_col_idx]).upper()
            if 'D' in row_shift_val: last_shift = "D"
            elif 'E' in row_shift_val: last_shift = "E"
            
            # 날짜 열들을 순회하며 데이터 확인
            for c_idx, date_list in date_col_map.items():
                cell_content = str(df.iloc[r_idx, c_idx])
                
                # 패턴: [숫자(병동)] + [이름]
                # 정규식 보강: 숫자와 이름 사이에 어떤 공백/줄바꿈이 있어도 인식
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]{2,4})', cell_content)
                
                if match:
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

# --- 3. UI 부분 ---
st.set_page_config(page_title="프라임 배정표 마스터", layout="wide")
st.title("🏥 프라임 배정표 전수 조사 추출기")

up_p = st.file_uploader("배정표 엑셀 파일을 올려주세요", type="xlsx")
selected_year = st.sidebar.selectbox("연도 설정", [2026, 2027])

if up_p:
    with st.spinner('데이터를 샅샅이 뒤지고 있습니다...'):
        try:
            df_plan = robust_extract_plan(up_p, selected_year)
            
            if not df_plan.empty:
                st.success(f"✅ 총 {len(df_plan)}개의 배정 이력을 찾아냈습니다!")
                st.dataframe(df_plan, use_container_width=True)
            else:
                st.warning("⚠️ 파일은 읽었으나 배정 데이터를 찾지 못했습니다. 엑셀에 [72 박소영]과 같이 병동과 이름이 한 칸에 있는지 확인해주세요.")
                # 디버깅용: 데이터가 어떻게 읽혔는지 첫 10줄 보여주기
                with st.expander("파일 읽기 디버깅 (프로그램이 본 데이터)"):
                    debug_df = pd.read_excel(up_p).head(10)
                    st.write(debug_df)
        except Exception as e:
            st.error(f"❌ 분석 중 예상치 못한 오류가 발생했습니다: {e}")
