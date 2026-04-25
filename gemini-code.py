import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [1. 데이터 파싱 공통 함수] ---
def parse_actual_work(cell_value):
    """P-D4/116 형식을 (근무: D, 병동: 116)으로 분리"""
    val = str(cell_value).strip()
    off_keywords = ['건', '필', 'ET', '/', 'nan', 'None', '']
    if not val.startswith('P-') and any(k in val for k in off_keywords):
        return "OFF", None
    
    match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
    if match:
        return match.group(1).upper(), match.group(2)
    return "OFF", None

def expand_plan_period(df_p, year=2026):
    """배정표의 기간(3/3~3/13)을 개별 날짜 행으로 확장"""
    expanded_rows = []
    for _, row in df_p.iterrows():
        try:
            # 기간 컬럼(예: '시작일~종료일' 형태의 데이터) 추출
            # 엑셀의 실제 컬럼명에 맞춰 수정 (여기서는 데이터 내용을 직접 파싱)
            period_str = str(row['시작일']) # '3/3' 형태와 '종료일' '3/13' 형태가 따로 있다면 합쳐서 처리
            # 만약 한 셀에 '3/3~3/13'이 있다면:
            if '~' in period_str:
                start_p, end_p = period_str.split('~')
            else:
                # 시작일과 종료일 컬럼이 따로 있는 일반적인 경우
                start_p = str(row['시작일'])
                end_p = str(row['종료일'])
            
            sm, sd = map(int, start_p.replace('월','').replace('일','').split('/'))
            em, ed = map(int, end_p.replace('월','').replace('일','').split('/'))
            
            curr_date = datetime(year, sm, sd)
            end_date = datetime(year, em, ed)
            
            while curr_date <= end_date:
                expanded_rows.append({
                    "날짜": curr_date.strftime('%Y-%m-%d'),
                    "근무": str(row['근무조']).strip(),
                    "병동": str(row['배정병동']).strip(),
                    "성함": str(row['간호사 성함']).strip()
                })
                curr_date += timedelta(days=1)
        except:
            continue
    return pd.DataFrame(expanded_rows)

# --- [2. UI 설정] ---
st.set_page_config(page_title="프라임 데이터 통합", layout="wide")
st.title("🏥 프라임 데이터 일자별 포맷 통합")

st.sidebar.header("📅 분석 기준")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)

col_plan, col_actual = st.columns(2)

# --- [3. 1단계: 배정표(Plan) 확장 및 정제] ---
with col_plan:
    st.header("1️⃣ 배정표 일자별 확장")
    file_p = st.file_uploader("주간 배정표(.xlsx) 업로드", type="xlsx", key="p")
    
    df_p_final = pd.DataFrame()
    if file_p:
        df_p_raw = pd.read_excel(file_p)
        # 확장 로직 실행
        df_p_final = expand_plan_period(df_p_raw, selected_year)
        
        if not df_p_final.empty:
            st.success("✅ 계획 데이터가 일자별로 확장되었습니다.")
            # 요청하신 순서: 날짜 - 근무 - 병동 - 성함
            st.dataframe(df_p_final[["날짜", "근무", "병동", "성함"]], use_container_width=True)

# --- [4. 2단계: 실제 근무표(Actual) 추출 및 정제] ---
with col_actual:
    st.header("2️⃣ 실제 근무표 형식 통일")
    file_a = st.file_uploader("월간 근무표(.xlsx) 업로드", type="xlsx", key="a")
    
    df_a_final = pd.DataFrame()
    if file_a:
        xl_a = pd.ExcelFile(file_a)
        sheet_a = st.selectbox("시트 선택", xl_a.sheet_names)
        df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
        
        # 시트명에서 월 추출
        month_num = re.sub(r'[^0-9]', '', sheet_a)
        actual_rows = []
        
        for _, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip()
            if name == 'nan' or len(name) < 2: continue
            
            for col_idx in range(7, len(df_a_raw.columns)):
                col_name = str(df_a_raw.columns[col_idx])
                day_match = re.search(r'\d+', col_name)
                
                if day_match:
                    day = day_match.group()
                    cell_val = row.iloc[col_idx]
                    shift, ward = parse_actual_work(cell_val)
                    
                    if shift != "OFF":
                        date_str = f"{selected_year}-{month_num.zfill(2)}-{day.zfill(2)}"
                        actual_rows.append({
                            "날짜": date_str,
                            "근무": shift,
                            "병동": ward,
                            "성함": name
                        })
        
        df_a_final = pd.DataFrame(actual_rows)
        if not df_a_final.empty:
            st.success("✅ 실제 근무 데이터 형식이 통일되었습니다.")
            # 요청하신 순서: 날짜 - 근무 - 병동 - 성함
            st.dataframe(df_a_final[["날짜", "근무", "병동", "성함"]], use_container_width=True)

# --- [5. 3단계: 통합 비교 분석] ---
st.markdown("---")
if not df_p_final.empty and not df_a_final.empty:
    if st.button("🚀 계획 vs 실제 정합성 분석 시작"):
        # 날짜와 성함을 기준으로 두 데이터 병합
        df_merge = pd.merge(
            df_a_final, 
            df_p_final, 
            on=["날짜", "성함"], 
            how="outer", 
            suffixes=("_실제", "_계획")
        )
        
        # 불일치 여부 체크 로직
        def check_diff(row):
            if pd.isna(row['병동_계획']): return "계획 외 지원"
            if pd.isna(row['병동_실제']): return "계획 미이행"
            if row['병동_실제'] != row['병동_계획']: return "병동 불일치"
            return "정상"

        df_merge['분석결과'] = df_merge.apply(check_diff, axis=1)
        
        st.subheader("🔍 최종 비교 분석 결과")
        st.dataframe(df_merge, use_container_width=True)
        
        # 요약 통계
        st.sidebar.markdown("### 📊 분석 요약")
        st.sidebar.write(df_merge['분석결과'].value_counts())
