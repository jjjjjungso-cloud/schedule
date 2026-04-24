import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. 날짜 확장 (3/30~4/10 -> 개별 날짜) ---
def expand_dates(date_text, year=2026):
    try:
        # 숫자와 ~ 외에는 다 제거
        clean_str = re.sub(r'[^0-9~]', '', str(date_text))
        if '~' not in clean_str: return []
        parts = clean_str.split('~')
        s_m, s_d = map(int, re.findall(r'\d+', parts[0]))
        s_date = datetime(year, s_m, s_d)
        e_nums = re.findall(r'\d+', parts[1])
        e_m = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_d = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        e_date = datetime(year, e_m, e_d)
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except: return []

# --- 2. 핀셋 추출 핵심 로직 ---
def simple_extract_plan(uploaded_file, year):
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    results = []
    exclude_names = ['고정민']

    for _, df in all_sheets.items():
        # [준비] 날짜가 있는 열(index)들 미리 찾아두기
        date_col_indices = [i for i, col in enumerate(df.columns) if '~' in str(col)]
        # [준비] 근무조(D/E)가 있는 열 위치 찾기
        shift_col_idx = next((i for i, col in enumerate(df.columns) if '근무조' in str(col)), 1)

        curr_shift = "D"
        for idx, row in df.iterrows():
            # 1. 근무조(행) 확인
            val_shift = str(row.iloc[shift_col_idx]).upper()
            if 'D' in val_shift: curr_shift = "D"
            elif 'E' in val_shift: curr_shift = "E"

            # 2. 날짜(열)를 돌며 데이터 추출
            for c_idx in date_col_indices:
                cell = str(row.iloc[c_idx])
                # [병동번호] + [이름] 패턴만 찾기 (예: "72\n박소영")
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell)
                
                if match:
                    ward, name = match.group(1), match.group(2)
                    if name in exclude_names: continue # 서무 제외

                    # 날짜 헤더에서 날짜 리스트 가져오기
                    date_header = df.columns[c_idx]
                    dates = expand_dates(date_header, year)
                    
                    for d in dates:
                        results.append({
                            '날짜': d.strftime('%Y-%m-%d'),
                            '근무조': curr_shift,
                            '성함': name,
                            '계획병동': ward # 여기서 이름을 '계획병동'으로 고정!
                        })
    return pd.DataFrame(results).drop_duplicates()

# --- 3. UI 구성 ---
st.title("🏥 프라임 배정표 핀셋 추출기")
year = st.sidebar.selectbox("연도", [2026, 2027])
up_p = st.file_uploader("배정표 엑셀 업로드", type="xlsx")

if up_p:
    df_plan = simple_extract_plan(up_p, year)
    if not df_plan.empty:
        st.success(f"✅ {len(df_plan)}개의 일별 데이터를 성공적으로 매칭했습니다!")
        st.dataframe(df_plan, use_container_width=True)
    else:
        st.error("데이터를 찾지 못했습니다. 셀 안에 [병동번호(엔터)이름] 형식이 맞는지 확인해주세요.")
        
# Step 2: 근무표 검증
elif step == "2. 근무표(Actual) 검증":
    st.header("📅 실제 근무표(Actual) 정제")
    up_a = st.file_uploader("근무표 업로드", type="xlsx")
    sel_month = st.sidebar.selectbox("해당 월 선택", [f"{i}월" for i in range(1, 13)])
    month_int = int(re.findall(r'\d+', sel_month)[0])
    if up_a:
        df_actual = clean_actual_data(up_a, selected_year, month_int, exclude_names)
        if not df_actual.empty:
            st.success(f"✅ {len(df_actual)}개의 근무 데이터를 정제했습니다.")
            st.dataframe(df_actual, use_container_width=True)
        else: st.warning("P- 코드를 찾지 못했습니다.")

# Step 3: 통합 비교 분석
elif step == "3. 통합 비교 분석":
    st.header("⚖️ 계획 vs 실제 통합 분석")
    c1, c2 = st.columns(2)
    with c1: up_p = st.file_uploader("배정표 업로드", type="xlsx", key="p3")
    with c2: up_a = st.file_uploader("근무표 업로드", type="xlsx", key="a3")
    sel_month = st.sidebar.selectbox("해당 월 선택", [f"{i}월" for i in range(1, 13)], key="m3")
    month_int = int(re.findall(r'\d+', sel_month)[0])

    if up_p and up_a:
        df_p = clean_plan_data(up_p, selected_year, exclude_names)
        df_a = clean_actual_data(up_a, selected_year, month_int, exclude_names)
        
        if not df_p.empty and not df_a.empty:
            # 날짜와 성함 기준 병합 (계획병동 컬럼명 주의!)
            merged = pd.merge(df_a, df_p, on=['날짜', '성함'], how='left', suffixes=('', '_계획'))
            
            def check_status(row):
                if pd.isna(row['계획병동']): return "기타(로그없음)"
                return "지원(순환)" if row['실제병동'] == row['계획병동'] else "결원대체"
            
            merged['상태'] = merged.apply(check_status, axis=1)
            
            st.subheader("📊 이번 달 운영 결과 요약")
            summary = merged.groupby(['성함', '상태']).size().unstack(fill_value=0)
            st.table(summary)
            
            with st.expander("🔍 상세 내역 보기"):
                st.dataframe(merged[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']], use_container_width=True)
        else:
            st.error("데이터 정제에 실패했습니다. 1단계와 2단계를 먼저 확인해주세요.")
