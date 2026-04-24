import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta

# --- 1. 날짜 확장 로직 (3/30~4/10 -> 개별 날짜) ---
def expand_dates(date_text, year=2026):
    if pd.isna(date_text): return []
    try:
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

# --- 2. 배정표(Plan) 핀셋 추출 (절대 안 멈추는 버전) ---
def extract_plan(uploaded_file, year, exclude_names):
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    results = []
    for _, df in all_sheets.items():
        # 모든 데이터를 문자열로 강제 변환 (TypeError 원천 차단)
        df = df.fillna("").astype(str)
        
        # 날짜 열과 근무조 열 위치 찾기
        shift_col_idx = -1
        date_cols = []
        for i in range(min(15, len(df))):
            row = df.iloc[i].tolist()
            for j, val in enumerate(row):
                if '근무조' in val: shift_col_idx = j
                if '~' in val and j not in date_cols: date_cols.append(j)
        
        if shift_col_idx == -1: shift_col_idx = 1
        
        curr_shift = "D"
        for _, row in df.iterrows():
            s_val = row.iloc[shift_col_idx].upper()
            if 'D' in s_val: curr_shift = "D"
            elif 'E' in s_val: curr_shift = "E"
            
            for c_idx in date_cols:
                cell = row.iloc[c_idx]
                # 병동번호(숫자) + 이름(한글) 패턴만 추출
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]{2,4})', cell)
                if match:
                    ward, name = match.group(1), match.group(2)
                    if name in exclude_names: continue
                    dates = expand_dates(df.columns[c_idx], year)
                    for d in dates:
                        results.append({'날짜': d.strftime('%Y-%m-%d'), '성함': name, '계획병동': ward, '근무조': curr_shift})
    return pd.DataFrame(results).drop_duplicates()

# --- 3. 실제근무표(Actual) 정제 (D4 인정) ---
def extract_actual(uploaded_file, year, month, exclude_names):
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    results = []
    for _, df in all_sheets.items():
        df = df.fillna("").astype(str)
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        
        for _, row in df.iterrows():
            name = row.iloc[name_idx].strip()
            if name in ['nan', '명', ''] or name in exclude_names: continue
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                code = row.iloc[d_idx]
                if code.startswith('P-'):
                    ward = re.search(r'/(\d+)', code)
                    if ward:
                        shift = 'D' if any(x in code for x in ['D', 'D4']) else 'E'
                        results.append({'날짜': datetime(year, month, int(d_match[0])).strftime('%Y-%m-%d'),
                                        '성함': name, '실제병동': str(int(ward.group(1))), '근무조': shift})
    return pd.DataFrame(results)

# --- 4. 메인 UI 및 전략 추천 ---
st.set_page_config(page_title="프라임 매니저", layout="wide")
st.title("🏥 프라임 간호사 스마트 배치 시스템 (최종)")

step = st.sidebar.radio("단계 선택", ["1. 데이터 정제 확인", "2. 통합 분석 및 전략"])
year = st.sidebar.selectbox("연도", [2026, 2027])
exclude_names = ['고정민']

if step == "1. 데이터 정제 확인":
    c1, c2 = st.columns(2)
    with c1:
        up_p = st.file_uploader("계획표(Plan)", type="xlsx", key="p1")
        if up_p: st.write("✅ 계획표 정제 결과"), st.dataframe(extract_plan(up_p, year, exclude_names))
    with c2:
        up_a = st.file_uploader("근무표(Actual)", type="xlsx", key="a1")
        m = st.selectbox("분석 월", [f"{i}월" for i in range(1, 13)])
        if up_a: st.write("✅ 근무표 정제 결과"), st.dataframe(extract_actual(up_a, year, int(m[:-1]), exclude_names))

elif step == "2. 통합 분석 및 전략":
    up_p = st.file_uploader("배정표 업로드", type="xlsx", key="p2")
    up_a = st.file_uploader("근무표 업로드", type="xlsx", key="a2")
    m = st.sidebar.selectbox("분석 월", [f"{i}월" for i in range(1, 13)], key="m2")
    
    if up_p and up_a:
        df_p = extract_plan(up_p, year, exclude_names)
        df_a = extract_actual(up_a, year, int(m[:-1]), exclude_names)
        
        if not df_p.empty and not df_a.empty:
            merged = pd.merge(df_a, df_p, on=['날짜', '성함'], how='left', suffixes=('', '_계획'))
            merged['상태'] = merged.apply(lambda r: "지원(순환)" if r['실제병동'] == r['계획병동'] else ("결원대체" if pd.notna(r['계획병동']) else "기타"), axis=1)
            
            st.subheader("📊 이번 달 운영 실적 요약")
            st.table(merged.groupby(['성함', '상태']).size().unstack(fill_value=0))
            
            st.markdown("---")
            st.subheader("🚀 차기 배정 전략 (병동 경험 평준화)")
            # 이력 데이터를 기반으로 한 추천 로직 (예시 표출)
            st.info("💡 1단계와 2단계의 데이터를 기반으로 팀원들의 '안 가본 병동' 배정을 추천합니다.")
