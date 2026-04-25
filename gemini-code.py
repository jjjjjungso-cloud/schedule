import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 구간 확장 (예: 4/13~24 -> 13~24일 전체 생성) ---
def expand_date_range(date_text, year=2026):
    if pd.isna(date_text): return []
    try:
        # 숫자와 ~ 외의 모든 노이즈 제거
        clean_text = re.sub(r'[^0-9~]', '', str(date_text))
        if '~' not in clean_text: return []
        
        parts = clean_text.split('~')
        start_nums = re.findall(r'\d+', parts[0])
        if len(start_nums) < 2: return []
        s_date = datetime(year, int(start_nums[0]), int(start_nums[1]))
        
        end_nums = re.findall(r'\d+', parts[1])
        if not end_nums: return []
        # '24'만 있을 경우 시작 월을 그대로 사용
        e_m = int(end_nums[0]) if len(end_nums) == 2 else s_date.month
        e_d = int(end_nums[1]) if len(e_nums) == 2 else int(end_nums[0])
        e_date = datetime(year, e_m, e_d)
        
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except: return []

# --- 2. 울트라 핀셋 추출 로직 ---
def ultra_extract_plan(uploaded_file, year):
    # 엔진을 'openpyxl'로 고정하여 호환성 높임
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None, engine='openpyxl')
    results = []
    exclude_names = ['고정민'] # 서무 선생님 제외

    for sheet_name, df in all_sheets.items():
        if df.shape[0] < 3: continue
        
        # 날짜와 근무조 열 찾기
        date_col_map = {}
        shift_col_idx = 0
        
        # 상단 20줄을 뒤져서 구조 파악
        for r_idx in range(min(20, len(df))):
            for c_idx in range(len(df.columns)):
                cell_val = str(df.iloc[r_idx, c_idx])
                if '~' in cell_val:
                    dates = expand_date_range(cell_val, year)
                    if dates: date_col_map[c_idx] = dates
                if '근무조' in cell_val or '조' == cell_val.strip():
                    shift_col_idx = c_idx

        # 데이터 본문 뒤지기
        last_shift = "D"
        for r_idx in range(len(df)):
            # 근무조 파악 (병합된 셀 대응)
            row_shift_val = str(df.iloc[r_idx, shift_col_idx]).upper()
            if 'D' in row_shift_val: last_shift = "D"
            elif 'E' in row_shift_val: last_shift = "E"
            
            for c_idx, date_list in date_col_map.items():
                cell_content = str(df.iloc[r_idx, c_idx])
                if cell_content in ['nan', 'None', '']: continue
                
                # [울트라 핀셋 정규식]
                # (\d{2,3}): 2~3자리 병동번호
                # [^가-힣]*?: 한글이 나오기 전까지의 모든 잡동사니(공백, 점선, 기호 등) 무시
                # ([가-힣]{2,4}): 2~4글자 이름
                pattern = re.compile(r'(\d{2,3})[^가-힣]*?([가-힣]{2,4})')
                matches = pattern.finditer(cell_content)
                
                for match in matches:
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
st.title("🏥 프라임 배정표 울트라 핀셋 추출기")
st.markdown("---")

col_set, col_main = st.columns([1, 3])

with col_set:
    st.subheader("⚙️ 설정")
    selected_year = st.selectbox("연도", [2026, 2027], index=0)
    up_file = st.file_uploader("배정표 엑셀 업로드", type="xlsx")

with col_main:
    if up_file:
        with st.spinner('데이터를 독하게(?) 낚아채는 중...'):
            df_plan = ultra_extract_plan(up_file, selected_year)
            
            if not df_plan.empty:
                st.success(f"✅ 드디어 {len(df_plan)}개의 데이터를 완벽하게 찾아냈습니다!")
                st.balloons() # 축하 세레머니!
                
                # 결과 테이블
                st.dataframe(df_plan.sort_values(by=['날짜', '성함']), use_container_width=True)
                
                # 다운로드 버튼 추가
                csv = df_plan.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 정제된 데이터 다운로드 (CSV)", csv, "prime_plan_data.csv", "text/csv")
            else:
                st.warning("아직 데이터를 찾지 못했습니다. 엑셀의 특정 칸을 복사해서 저에게 채팅으로 붙여넣어 주시면 더 정확히 분석해 드릴게요!")
                
                # 디버깅: 컴퓨터가 실제로는 어떻게 글자를 읽고 있는지 보여줌
                with st.expander("🔍 컴퓨터가 읽은 원본 데이터 보기 (디버깅)"):
                    raw_df = pd.read_excel(up_file, header=None).astype(str)
                    st.write(raw_df.head(20))
