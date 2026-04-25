import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [1. 데이터 파싱 공통 함수] ---
def parse_actual_work(cell_value):
    """실제 근무표용: P-D4/116 형식을 (근무: D, 병동: 116)으로 분리"""
    val = str(cell_value).strip()
    off_keywords = ['건', '필', 'ET', '/', 'nan', 'None', '']
    if not val.startswith('P-') and (any(k in val for k in off_keywords) or val == ''):
        return "OFF", None
    
    match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
    if match:
        return match.group(1).upper(), match.group(2)
    return "OFF", None

def expand_plan_period_board(df_p, year=2026):
    """
    배정표(계획)용: 게시판 형태(셀 내 줄바꿈, 헤더에 기간) 분석 및 확장
    """
    expanded_rows = []
    
    # 날짜 기간이 포함된 컬럼(예: '4/13~24') 추출
    date_cols = [c for c in df_p.columns if '~' in str(c)]
    
    for _, row in df_p.iterrows():
        # 보통 B열(index 1)이 근무조(D, E, N)
        shift = str(row.iloc[1]).strip().upper()
        if shift not in ['D', 'E', 'N']: continue 
        
        for col_name in date_cols:
            cell_content = str(row[col_name])
            if cell_content == 'nan' or not cell_content.strip(): continue
            
            # 셀 내부에 '병동\n이름' 형태로 데이터가 있는 경우 분리
            lines = cell_content.split('\n')
            if len(lines) < 2: continue # 병동과 이름이 모두 있어야 함
            
            ward = lines[0].strip()
            name = lines[1].strip()
            
            # 컬럼 헤더에서 날짜 정보 추출 (예: "4/13~24")
            try:
                date_parts = re.findall(r'\d+', col_name)
                month = int(date_parts[0])
                start_day = int(date_parts[1])
                end_day = int(date_parts[2])
                
                start_dt = datetime(year, month, start_day)
                # 종료일이 시작일보다 작으면 월이 넘어간 것으로 간주할 수 있으나 
                # 여기서는 같은 달 내로 가정 (필요시 월 변경 로직 추가 가능)
                end_dt = datetime(year, month, end_day)
                
                curr = start_dt
                while curr <= end_dt:
                    # 주말 제외 (평일만 지원하는 경우)
                    if curr.weekday() < 5: 
                        expanded_rows.append({
                            "날짜": curr.strftime('%Y-%m-%d'),
                            "근무": shift,
                            "병동": ward,
                            "성함": name
                        })
                    curr += timedelta(days=1)
            except:
                continue
                
    return pd.DataFrame(expanded_rows)

# --- [2. UI 설정] ---
st.set_page_config(page_title="프라임 통합 분석 시스템", layout="wide")
st.title("🏥 프라임 데이터 통합 분석 및 정합성 검증")

st.sidebar.header("📅 분석 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month_sidebar = st.sidebar.selectbox("대상 월(참고용)", [f"{i}월" for i in range(1, 13)], index=3)

col_plan, col_actual = st.columns(2)

# --- [3. 1단계: 배정표(Plan) 정제 및 확장] ---
df_p_final = pd.DataFrame()
with col_plan:
    st.header("1️⃣ 배정표(계획) 일자별 확장")
    file_p = st.file_uploader("게시판형 배정표(.xlsx) 업로드", type="xlsx", key="p")
    if file_p:
        # 게시판 형태는 첫 행이 날짜 헤더인 경우가 많으므로 기본 읽기
        df_p_raw = pd.read_excel(file_p)
        df_p_final = expand_plan_period_board(df_p_raw, selected_year)
        
        if not df_p_final.empty:
            st.success(f"✅ 계획 데이터 {len(df_p_final)}건 확장 완료")
            st.dataframe(df_p_final[["날짜", "근무", "병동", "성함"]], use_container_width=True)
        else:
            st.warning("배정표 형식을 인식하지 못했습니다. 셀 내 줄바꿈(Alt+Enter) 여부를 확인하세요.")

# --- [4. 2단계: 실제 근무표(Actual) 추출] ---
df_a_final = pd.DataFrame()
with col_actual:
    st.header("2️⃣ 실제 근무표(실제) 형식 통일")
    file_a = st.file_uploader("월간 근무표(.xlsx) 업로드", type="xlsx", key="a")
    if file_a:
        xl_a = pd.ExcelFile(file_a)
        sheet_a = st.selectbox("분석할 월(시트) 선택", xl_a.sheet_names)
        df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
        
        # 1일이 시작되는 열 자동 찾기
        start_col_idx = next((i for i, col in enumerate(df_a_raw.columns) if '1' in str(col)), 7)
        
        # 시트 이름에서 월 추출
        extracted_month = re.sub(r'[^0-9]', '', sheet_a)
        if not extracted_month: extracted_month = re.sub(r'[^0-9]', '', selected_month_sidebar)

        actual_rows = []
        for index, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip() # C열 성함
            if name == 'nan' or len(name) < 2: continue
            
            for col_idx in range(start_col_idx, len(df_a_raw.columns)):
                col_name = str(df_a_raw.columns[col_idx])
                day_match = re.search(r'\d+', col_name)
                
                if day_match:
                    day = day_match.group()
                    cell_val = row.iloc[col_idx]
                    shift, ward = parse_actual_work(cell_val)
                    
                    if shift != "OFF":
                        date_str = f"{selected_year}-{extracted_month.zfill(2)}-{day.zfill(2)}"
                        actual_rows.append({
                            "날짜": date_str,
                            "근무": shift,
                            "병동": ward,
                            "성함": name
                        })
        
        df_a_final = pd.DataFrame(actual_rows)
        if not df_a_final.empty:
            st.success(f"✅ {extracted_month}월 실제 근무 데이터 추출 완료")
            st.dataframe(df_a_final[["날짜", "근무", "병동", "성함"]], use_container_width=True)

# --- [5. 3단계: 통합 비교 분석] ---
st.markdown("---")
if not df_p_final.empty and not df_a_final.empty:
    if st.button("🚀 계획 vs 실제 정합성 분석 시작"):
        # 날짜와 성함을 기준으로 병합
        df_merge = pd.merge(
            df_a_final, 
            df_p_final, 
            on=["날짜", "성함"], 
            how="outer", 
            suffixes=("_실제", "_계획")
        )
        
        def check_diff(row):
            if pd.isna(row['병동_계획']): return "계획 외 지원"
            if pd.isna(row['병동_실제']): return "계획 미이행"
            if str(row['병동_실제']) != str(row['병동_계획']): return "병동 불일치"
            return "정상"

        df_merge['분석결과'] = df_merge.apply(check_diff, axis=1)
        
        st.subheader("🔍 최종 비교 분석 결과")
        st.dataframe(df_merge, use_container_width=True)
        
        # 사이드바 통계 요약
        st.sidebar.markdown("### 📊 분석 요약")
        st.sidebar.write(df_merge['분석결과'].value_counts())
