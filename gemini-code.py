import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 구간 확장 (3/3~3/13 -> 3일부터 13일까지 개별 날짜 생성) ---
def expand_dates(date_text, year=2026):
    if pd.isna(date_text): return []
    try:
        # 숫자와 ~ 외의 문자 제거
        clean_text = re.sub(r'[^0-9~]', '', str(date_text))
        if '~' not in clean_text: return []
        
        parts = clean_text.split('~')
        s_m, s_d = map(int, re.findall(r'\d+', parts[0]))
        s_date = datetime(year, s_m, s_d)
        
        e_nums = re.findall(r'\d+', parts[1])
        # 종료 월이 없으면 시작 월을 그대로 사용 (예: 3/3~13)
        e_m = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_d = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        e_date = datetime(year, e_m, e_d)
        
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except:
        return []

# --- 2. 소영님의 "눈" 로직 (세로축 근무조 + 가로축 날짜 매칭) ---
def extract_prime_logic(uploaded_file, year):
    # 모든 데이터를 일단 읽어옴 (Header 없음)
    df = pd.read_excel(uploaded_file, header=None, engine='openpyxl')
    
    date_cols = {} # {열번호: [날짜리스트]}
    shift_col_idx = -1
    
    # [Step 1] 시트 상단을 뒤져서 날짜 열과 근무조 열의 위치를 파악
    for r in range(min(15, len(df))):
        for c in range(len(df.columns)):
            val = df.iloc[r, c]
            if pd.notna(val):
                val_str = str(val) # 에러 방지: 모든 값을 문자로 변환
                if '~' in val_str:
                    dates = expand_dates(val_str, year)
                    if dates: date_cols[c] = dates
                if '근무조' in val_str:
                    shift_col_idx = c
    
    # 근무조 열을 못 찾았을 경우 대비 (보통 2~3번째 열)
    if shift_col_idx == -1: shift_col_idx = 1
    
    results = []
    current_shift = "D" # 기본값
    exclude_names = ['고정민'] # 서무 제외

    # [Step 2] 행 단위로 내려가며 데이터 추출
    for r in range(len(df)):
        # 1. 근무조 확인 (소영님 로직: D/E가 있으면 업데이트, 없으면 위에서 가져옴)
        raw_shift = str(df.iloc[r, shift_col_idx]).strip().upper()
        if 'D' in raw_shift: current_shift = 'D'
        elif 'E' in raw_shift: current_shift = 'E'
        
        # 2. 날짜 열들을 순회하며 [숫자 + 이름] 찾기
        for c, date_list in date_cols.items():
            cell_val = str(df.iloc[r, c])
            # 패턴: [병동번호(숫자)] + [공백] + [이름(한글)]
            match = re.search(r'(\d+)\s+([가-힣]{2,4})', cell_val)
            
            if match:
                ward = match.group(1)
                name = match.group(2)
                
                if name in exclude_names: continue
                
                for d in date_list:
                    results.append({
                        '날짜': d.strftime('%Y-%m-%d'),
                        '성함': name,
                        '계획병동': ward,
                        '근무조': current_shift
                    })
                    
    return pd.DataFrame(results).drop_duplicates()

# --- 3. UI 구성 ---
st.set_page_config(page_title="프라임 매니저", layout="wide")
st.title("🏥 프라임 간호사 배정표 지능형 추출기")

selected_year = st.sidebar.selectbox("연도 설정", [2026, 2027], index=0)
up_file = st.file_uploader("배정표 엑셀 업로드", type="xlsx")

if up_file:
    with st.spinner('데이터를 정제하는 중...'):
        try:
            df_result = extract_prime_logic(up_file, selected_year)
            if not df_result.empty:
                st.success("✅ 데이터를 성공적으로 읽어왔습니다!")
                st.dataframe(df_result, use_container_width=True)
                
                # 통계 요약 (소영님 확인용)
                st.subheader("👤 간호사별 대기 배정 현황")
                st.table(df_result['성함'].value_counts())
            else:
                st.warning("데이터를 찾지 못했습니다. 엑셀의 [72 정소영] 형식을 확인해주세요.")
        except Exception as e:
            st.error(f"⚠️ 분석 중 오류가 발생했습니다: {e}")
            st.info("엑셀 파일의 시트 구조나 날짜 형식이 평소와 다른지 확인이 필요합니다.")
