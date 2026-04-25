import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 덩어리 쪼개기 (3/3~3/13 -> 매일매일의 날짜로) ---
def expand_date_range(date_text, year=2026):
    try:
        # 숫자와 ~ 기호만 남기고 정제
        clean_text = re.sub(r'[^0-9~]', '', str(date_text))
        if '~' not in clean_text: return []
        
        parts = clean_text.split('~')
        start_m, start_d = map(int, re.findall(r'\d+', parts[0]))
        start_date = datetime(year, start_m, start_d)
        
        end_nums = re.findall(r'\d+', parts[1])
        end_m = int(end_nums[0]) if len(end_nums) == 2 else start_date.month
        end_d = int(end_nums[1]) if len(end_nums) == 2 else int(end_nums[0])
        end_date = datetime(year, end_m, end_d)
        
        return [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    except:
        return []

# --- 2. 소영님의 "행렬 매칭" 로직 구현 ---
def extract_plan_logic(uploaded_file, year):
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    results = []
    exclude_names = ['고정민']

    for _, df in all_sheets.items():
        # 날짜 헤더가 있는 열 번호들 찾기
        date_cols = [i for i, col in enumerate(df.columns) if '~' in str(col)]
        # '근무조' 글자가 있는 열 찾기
        shift_col_idx = next((i for i, col in enumerate(df.columns) if '근무조' in str(col)), 1)

        last_seen_shift = "D" # 병합된 셀을 위해 마지막 근무조 기억
        
        for _, row in df.iterrows():
            # [세로축 확인] 현재 행의 근무조 파악
            shift_val = str(row.iloc[shift_col_idx]).upper()
            if 'D' in shift_val: last_seen_shift = "D"
            elif 'E' in shift_val: last_seen_shift = "E"
            # (만약 빈 칸이면 위에서 정해진 last_seen_shift를 그대로 씀)

            # [가로축 확인] 날짜 열들을 하나씩 검사
            for c_idx in date_cols:
                cell_content = str(row.iloc[c_idx])
                
                # [핀셋 추출] "숫자(병동) + 이름" 패턴 찾기
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell_content)
                
                if match:
                    ward_no = match.group(1)
                    nurse_name = match.group(2)
                    
                    if nurse_name in exclude_names: continue

                    # 날짜 구간을 개별 날짜로 풀어서 저장
                    date_header = str(df.columns[c_idx])
                    target_dates = expand_date_range(date_header, year)
                    
                    for d in target_dates:
                        results.append({
                            '날짜': d.strftime('%Y-%m-%d'),
                            '근무조': last_seen_shift,
                            '성함': nurse_name,
                            '계획병동': ward_no
                        })
                        
    return pd.DataFrame(results).drop_duplicates()

# --- 3. UI 부분 ---
st.title("🏥 프라임 배정표 매트릭스 추출기")
st.sidebar.write("소영님의 직관적인 매칭 원리를 반영한 버전입니다.")

up_p = st.file_uploader("배정표(Plan) 엑셀을 올려주세요", type="xlsx")
year = st.sidebar.selectbox("연도", [2026, 2027])

if up_p:
    with st.spinner('행과 열을 매칭하는 중...'):
        df_plan = extract_plan_logic(up_p, year)
    
    if not df_plan.empty:
        st.success(f"✅ {len(df_plan)}일치 배정 데이터를 완벽하게 찾아냈습니다!")
        st.dataframe(df_plan, use_container_width=True)
    else:
        st.error("데이터를 찾지 못했습니다. 엑셀의 '날짜(~)'와 '병동 이름' 형식을 확인해 주세요.")
