import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [공통 함수] 데이터 파싱 엔진 ---
def parse_work_cell(val):
    """P-D4/116 -> (D, 116) 추출 / 휴무 및 기타는 OFF 반환"""
    val = str(val).strip()
    if not val.startswith('P-'):
        return "OFF", None
    # D4, D6 등 숫자가 붙어도 첫 알파벳만 가져오고, / 뒤의 병동 숫자 추출
    match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
    if match:
        return match.group(1).upper(), match.group(2)
    return "OFF", None

def expand_march_dates(date_range_str, year=2026):
    """'3/3~3/13' 형태를 개별 날짜 리스트로 변환"""
    try:
        start_s, end_s = date_range_str.split('~')
        sm, sd = map(int, start_s.split('/'))
        em, ed = map(int, end_s.split('/'))
        start_dt = datetime(year, sm, sd)
        end_dt = datetime(year, em, ed)
        
        dates = []
        curr = start_dt
        while curr <= end_dt:
            dates.append(curr.strftime('%Y-%m-%d'))
            curr += timedelta(days=1)
        return dates
    except:
        return []

# --- [UI 설정] ---
st.set_page_config(page_title="프라임 근무 분석 시스템", layout="wide")
st.title("🏥 프라임 간호사 지원근무 정합성 분석")
st.sidebar.header("📅 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("대상 월", [f"{i}월" for i in range(1, 13)], index=3)

# --- [1단계: 배정표(Plan) 정제] ---
st.header("1️⃣ 배정표(Plan) 데이터 정제")
file_p = st.file_uploader("주간 배정표(.xlsx) 업로드", type="xlsx", key="plan")

df_plan_std = pd.DataFrame()

if file_p:
    xl_p = pd.ExcelFile(file_p)
    sheet_p = st.selectbox("계획 시트 선택", xl_p.sheet_names)
    df_p_raw = pd.read_excel(file_p, sheet_name=sheet_p)
    
    # 4-5월 열 기준(E, H, I, L, O)으로 성함과 병동 정보 추출
    # 실제 데이터 구조에 따라 index(4, 7, 8...)는 조정 가능합니다.
    plan_rows = []
    for _, row in df_p_raw.iterrows():
        name = str(row.iloc[4]).split()[0] if pd.notsuffix(row.iloc[4], 'nan') else None # E열 성함
        if not name or name == 'nan': continue
        
        # 계획 데이터에 날짜 정보가 있다면 매칭 (여기서는 예시로 '날짜'열 가정)
        # 만약 날짜가 기간으로 되어있다면 expand_march_dates 사용 가능
        plan_rows.append({"성함": name, "계획병동": str(row.iloc[7]), "구분": "Plan"})
        
    df_plan_std = pd.DataFrame(plan_rows)
    st.success("✅ 배정표 정제 완료")
    st.dataframe(df_plan_std.head())

st.markdown("---")

# --- [2단계: 실제 근무표(Actual) 정제] ---
st.header("2️⃣ 실제 근무표(Actual) 데이터 정제")
file_a = st.file_uploader("월간 근무표(.xlsx) 업로드", type="xlsx", key="actual")

df_actual_std = pd.DataFrame()

if file_a:
    xl_a = pd.ExcelFile(file_a)
    sheet_a = st.selectbox("실제 근무 시트 선택", xl_a.sheet_names)
    df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
    
    actual_rows = []
    month_num = re.sub(r'[^0-9]', '', selected_month)

    # 3월 특수 구조 처리
    if "3월" in selected_month:
        for _, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip()
            for cell in row:
                if '~' in str(cell) and '/' in str(cell):
                    dates = expand_march_dates(str(cell), selected_year)
                    shift, ward = parse_work_cell(row.iloc[3]) # 예시 위치
                    for d in dates:
                        actual_rows.append({"성함": name, "날짜": d, "근무": shift, "실제병동": ward})
    # 4-5월 일반 구조 처리
    else:
        for _, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip() # C열 성함
            if name == 'nan': continue
            for col_idx in range(7, len(df_a_raw.columns)): # H열부터 날짜
                day_match = re.search(r'\d+', str(df_a_raw.columns[col_idx]))
                if day_match:
                    day = day_match.group()
                    shift, ward = parse_work_cell(row.iloc[col_idx])
                    if shift != "OFF":
                        date_str = f"{selected_year}-{month_num.zfill(2)}-{day.zfill(2)}"
                        actual_rows.append({"성함": name, "날짜": date_str, "근무": shift, "실제병동": ward})
    
    df_actual_std = pd.DataFrame(actual_rows)
    st.success("✅ 실제 근무표 일자별 정제 완료")
    st.dataframe(df_actual_std.head())

# --- [3단계: 정합성 비교 분석] ---
st.markdown("---")
st.header("3️⃣ 계획 vs 실제 데이터 비교")

if not df_plan_std.empty and not df_actual_std.empty:
    # 성함을 기준으로 두 데이터 병합 (날짜까지 있다면 on=['성함', '날짜'])
    df_merge = pd.merge(df_actual_std, df_plan_std, on="성함", how="left")
    
    # 일치 여부 확인 (계획병동과 실제병동 비교)
    df_merge['일치여부'] = df_merge.apply(
        lambda x: "✅ 일치" if str(x['실제병동']) in str(x['계획병동']) else "❌ 불일치", axis=1
    )
    
    st.subheader("🔍 최종 분석 결과")
    st.dataframe(df_merge, use_container_width=True)
    
    # 불일치 데이터만 따로 보기
    diff_count = len(df_merge[df_merge['일치여부'] == "❌ 불일치"])
    if diff_count > 0:
        st.warning(f"⚠️ 계획과 다른 근무가 {diff_count}건 발견되었습니다.")
        st.dataframe(df_merge[df_merge['일치여부'] == "❌ 불일치"])
    else:
        st.balloons()
        st.success("모든 근무가 계획대로 이행되었습니다!")
else:
    st.info("💡 분석을 위해 배정표와 근무표를 모두 업로드해주세요.")
