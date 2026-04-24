import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta
import io

# --- 1. DB 및 초기화 설정 ---
def init_db():
    conn = sqlite3.connect('prime_nurse_system.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS nurses (
                    name TEXT PRIMARY KEY, unit TEXT, sub_count INTEGER DEFAULT 0,
                    last_d_dedicated TEXT, visited_wards TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS assignment_logs (
                    date TEXT, name TEXT, plan_ward TEXT, actual_ward TEXT,
                    shift TEXT, status TEXT, UNIQUE(date, name))''')
    conn.commit()
    conn.close()

def get_nurses_list():
    """서무 업무자 제외한 13명 리스트"""
    return [
        ('정윤정', '1동'), ('최휘영', '1동'), ('기아현', '1동'), ('김유진', '1동'),
        ('정하라', '1동'), ('박소영', '1동'), ('박가영', '1동'),
        ('정소영', '2동'), ('홍현의', '2동'), ('문선희', '2동'), ('김민정', '2동'),
        ('김한솔', '2동'), ('이선아', '2동')
    ]

# --- 2. 데이터 정제 핵심 엔진 (개별 작동) ---

def safe_expand_dates(date_str, year):
    if pd.isna(date_str) or '~' not in str(date_str): return []
    try:
        clean_str = re.sub(r'[^0-9~/]', '', str(date_str))
        parts = clean_str.split('~')
        s_nums = re.findall(r'\d+', parts[0])
        s_date = datetime(year, int(s_nums[0]), int(s_nums[1]))
        e_nums = re.findall(r'\d+', parts[1])
        e_month = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_day = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        e_date = datetime(year, e_month, e_day)
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except: return []

# --- 3. UI 구성 ---

st.set_page_config(page_title="프라임 매니저", layout="wide")
init_db()

st.title("🏥 프라임 간호사 실무 데이터 단계별 검증")
st.sidebar.header("🔍 분석 단계 선택")
step = st.sidebar.radio("작업 선택", ["1. 배정표(Plan) 검증", "2. 근무표(Actual) 검증", "3. 통합 비교 분석"])

selected_year = st.sidebar.selectbox("연도", [2026, 2027])
exclude_names = ['고정민']

# --- Step 1: 배정표(Plan)만 분석 ---
if step == "1. 배정표(Plan) 검증":
    st.header("📋 대기배정표(Plan) 데이터 정제")
    up_p = st.file_uploader("배정표 엑셀 업로드", type="xlsx")


    import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

def expand_dates(date_str, year=2026):
    """'3/30~4/10' 형태의 헤더를 날짜 리스트로 변환"""
    try:
        # 숫자와 ~ 기호만 남기고 정리
        clean_str = re.sub(r'[^0-9~]', '', str(date_str))
        if '~' not in clean_str: return []
        
        parts = clean_str.split('~')
        s_month, s_day = map(int, re.findall(r'\d+', parts[0]))
        s_date = datetime(year, s_month, s_day)
        
        e_nums = re.findall(r'\d+', parts[1])
        e_month = int(e_nums[0]) if len(e_nums) == 2 else s_date.month
        e_day = int(e_nums[1]) if len(e_nums) == 2 else int(e_nums[0])
        e_date = datetime(year, e_month, e_day)
        
        return [s_date + timedelta(days=x) for x in range((e_date - s_date).days + 1)]
    except:
        return []

def extract_plan_data(uploaded_file, year):
    # 제외 대상
    exclude_names = ['고정민']
    
    # 모든 시트 읽기
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    all_results = []

    for sheet_name, df in all_sheets.items():
        # 1. '근무조' 열과 '날짜(~)' 열 위치 찾기
        shift_col_idx = -1
        date_cols = []
        
        # 헤더와 상단 10줄 스캔하여 위치 파악
        for i in range(min(10, len(df))):
            row_values = df.iloc[i].astype(str).tolist()
            for j, val in enumerate(row_values):
                if '근무조' in val: shift_col_idx = j
                if '~' in val and j not in date_cols: date_cols.append(j)
        
        # 만약 헤더(columns)에 날짜가 있다면 추가
        for j, col in enumerate(df.columns):
            if '~' in str(col) and j not in date_cols: date_cols.append(j)

        if shift_col_idx == -1: shift_col_idx = 1 # 기본값

        # 2. 데이터 행 순회
        current_shift = "D"
        for idx, row in df.iterrows():
            # 근무조 업데이트 (D/E)
            shift_val = str(row.iloc[shift_col_idx]).upper()
            if 'D' in shift_val: current_shift = "D"
            elif 'E' in shift_val: current_shift = "E"
            
            # 각 날짜 열 확인
            for c_idx in date_cols:
                cell_val = str(row.iloc[c_idx])
                
                # 핵심 패턴: [숫자(병동)] + [줄바꿈/공백] + [한글이름]
                # 예: "72\n박소영" 또는 "101 김유진"
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell_val)
                
                if match:
                    ward = match.group(1)
                    name = match.group(2)
                    
                    if name in exclude_names: continue
                    
                    # 날짜 텍스트 가져오기 (열 제목 또는 셀 자체)
                    date_header = str(df.columns[c_idx])
                    target_dates = expand_dates(date_header if '~' in date_header else cell_val, year)
                    
                    for d in target_dates:
                        all_results.append({
                            '날짜': d.strftime('%Y-%m-%d'),
                            '근무조': current_shift,
                            '이름': name,
                            '계획병동': ward
                        })
                        
    return pd.DataFrame(all_results).drop_duplicates()

# --- Streamlit UI 부분 ---
st.title("🏥 프라임 배정표 데이터 핀셋 추출기")
selected_year = st.sidebar.selectbox("연도 설정", [2026, 2027], index=0)

up_p = st.file_uploader("대기배정표(Plan) 엑셀 파일을 올려주세요", type="xlsx")

if up_p:
    with st.spinner('불필요한 데이터를 제외하고 핵심만 뽑아내는 중...'):
        df_plan = extract_plan_data(up_p, selected_year)
        
    if not df_plan.empty:
        st.success(f"✅ 총 {len(df_plan)}개의 일별 배정 데이터를 추출했습니다.")
        st.dataframe(df_plan, use_container_width=True)
        
        # 간단한 요약
        st.subheader("👤 간호사별 배정 횟수")
        st.bar_chart(df_plan['이름'].value_counts())
    else:
        st.error("데이터를 찾지 못했습니다. 셀 안에 '병동번호(엔터)이름' 형식이 맞는지 확인해주세요.")

# --- Step 2: 근무표(Actual)만 분석 ---
elif step == "2. 근무표(Actual) 검증":
    st.header("📅 실제 근무스케줄(Actual) 데이터 정제")
    up_a = st.file_uploader("근무표 엑셀 업로드", type="xlsx")
    selected_month = st.sidebar.selectbox("해당 월 선택", [f"{i}월" for i in range(1, 13)])
    month_int = int(re.findall(r'\d+', selected_month)[0])

    if up_a:
        try:
            a_sheets = pd.read_excel(up_a, sheet_name=None)
            actual_list = []
            for _, df in a_sheets.items():
                name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
                day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
                for _, row in df.iterrows():
                    name = str(row.iloc[name_idx]).strip()
                    if name in ['nan', '명', ''] or name in exclude_names: continue
                    for d_idx in day_cols:
                        d_num = re.findall(r'\d+', str(df.columns[d_idx]))[0]
                        code = str(row.iloc[d_idx])
                        if code.startswith('P-'):
                            ward = re.search(r'/(\d+)', code)
                            if ward:
                                actual_list.append({
                                    '날짜': datetime(selected_year, month_int, int(d_num)).strftime('%Y-%m-%d'),
                                    '성함': name, '실제병동': str(int(ward.group(1))), '코드': code
                                })
            
            df_actual = pd.DataFrame(actual_list)
            if not df_actual.empty:
                st.success("✅ 근무표 정제 완료!")
                st.dataframe(df_actual, use_container_width=True)
            else:
                st.warning("P- 코드로 시작하는 데이터를 찾지 못했습니다.")
        except Exception as e:
            st.error(f"오류 발생: {e}")

# --- Step 3: 통합 비교 ---
elif step == "3. 통합 비교 분석":
    st.header("⚖️ 계획 vs 실제 비교 분석 (최종 결과)")
    st.write("1단계와 2단계에서 검증된 데이터를 바탕으로 통합 리포트를 생성합니다.")
    # (여기서 앞선 로직을 합친 통합 분석 코드가 실행됨)
    st.info("사이드바에서 파일 업로드 후 검증이 완료되면 이곳에 '지원/결원대체' 결과가 표시됩니다.")
