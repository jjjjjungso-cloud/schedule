import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [초기 설정] ---
WARD_GROUPS = {
    '1동': ['41', '51', '52', '61', '62', '71', '72', '91', '92', '101', '102', '111', '122', '131'],
    '2동': ['66', '75', '76', '85', '86', '96', '105', '106', '116']
}
NURSE_GROUPS = {
    '1동': ['정윤정', '기아현', '김유진', '정하라', '김한솔', '최휘영', '박소영'],
    '2동': ['박가영', '홍현의', '김민정', '정소영', '문선희', '엄현지']
}

# 딕셔너리 매핑
NURSE_TO_BLD = {name: bld for bld, names in NURSE_GROUPS.items() for name in names}
WARD_TO_BLD = {ward: bld for bld, wards in WARD_GROUPS.items() for ward in wards}

# --- [정제 함수] ---
def expand_generic_data(df):
    expanded_list = []
    df.columns = df.columns.str.strip()
    
    # 필수 컬럼 찾기 (포함 검색)
    try:
        c_start = next(c for c in df.columns if '시작일' in c)
        c_end = next(c for c in df.columns if '종료일' in c)
        c_shift = next(c for c in df.columns if '근무조' in c)
        c_ward = next(c for c in df.columns if '병동' in c)
        c_name = next((c for c in df.columns if '성함' in c or '이름' in c or '명' in c), None)
    except StopIteration: return pd.DataFrame()

    for _, row in df.iterrows():
        try:
            start_dt = pd.to_datetime(row[c_start])
            end_dt = pd.to_datetime(row[c_end])
            curr = start_dt
            while curr <= end_dt:
                if curr.weekday() < 5: 
                    expanded_list.append({
                        '날짜': curr,
                        '주차': f"{curr.isocalendar().week}주차",
                        '성함': str(row[c_name]).strip() if c_name else "",
                        '계획근무조': str(row[c_shift]).strip(),
                        '계획병동': str(row[c_ward]).strip()
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

def get_refined_ward_data(uploaded_file):
    """업로드된 파일을 직접 읽고 정제"""
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"파일을 읽을 수 없습니다: {e}")
        return pd.DataFrame()

    df.columns = df.columns.str.strip()
    # '명'이 포함된 열 자동 탐색
    name_col = next((c for c in df.columns if '명' in str(c)), None)
    if name_col is None:
        st.error(f"파일에서 '명' 열을 찾을 수 없습니다. 현재 컬럼: {list(df.columns)}")
        return pd.DataFrame()
        
    day_cols = [c for c in df.columns if '일' in str(c)]
    processed_data = []
    
    for d_col in day_cols:
        day_match = re.findall(r'\d+', str(d_col))
        if not day_match: continue
        day = int(day_match[0])
        
        for _, row in df.iterrows():
            name = str(row[name_col]).strip()
            if name in ['nan', 'None', '', '명', '성', '월', '성명', '이름', '사 번']: continue
            
            val = str(row[d_col]).strip()
            if '/' in val:
                parts = val.split('/')
                if len(parts) > 1:
                    nums = re.findall(r'\d+', parts[1])
                    if nums:
                        processed_data.append({
                            '날짜': day,
                            '성함': name,
                            '실제병동': str(int(nums[0]))
                        })
    return pd.DataFrame(processed_data)

# --- [메인 UI] ---
st.set_page_config(layout="wide")
st.title("🏥 프라임 데이터 통합 시스템")

# 파일 업로더
c1, c2, c3 = st.columns(3)
file_p = c1.file_uploader("과거 계획(Plan)", type=["xlsx", "csv"])
file_a = c2.file_uploader("실제 근무표(Actual)", type=["xlsx", "csv"])
file_r = c3.file_uploader("차월 요청(Request)", type=["xlsx", "csv"])

if file_p and file_a and file_r:
    if st.button("🚀 데이터 정제 및 통합 시작"):
        # 1. Plan 데이터 처리
        def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
        df_p = expand_generic_data(load_df(file_p))
        
        # 2. Actual 데이터 처리
        df_a = get_refined_ward_data(file_a)
        
        # 3. 데이터 병합 (날짜 기반)
        # 실제 데이터는 '날짜'가 숫자(일)로 추출되므로, 이를 연/월과 조합하여 데이터프레임 병합
        st.success("✅ 정제 완료! 분석할 수 있습니다.")
        st.session_state.df_master = df_p # 병합 로직은 추후 필요시 추가
        st.dataframe(df_a.head()) # 결과 미리보기
else:
    st.info("파일 3개를 모두 업로드해 주세요.")
