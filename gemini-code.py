import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [1. 핵심 파싱 함수] ---
def parse_actual_work(cell_value):
    val = str(cell_value).strip()
    off_keywords = ['건', '필', 'ET', '/', 'nan', 'None', '']
    if not val.startswith('P-') and (any(k in val for k in off_keywords) or val == ''):
        return "OFF", None
    match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
    if match:
        return match.group(1).upper(), match.group(2)
    return "OFF", None

def expand_plan_period_board(df_p, year=2026):
    """배정표(계획): 사진 양식에 맞춰 인덱스 및 텍스트 분리 로직 강화"""
    expanded_rows = []
    
    # 1. 날짜 기간이 포함된 컬럼(예: '3/2~3/13') 모두 찾기
    date_cols = [c for c in df_p.columns if '~' in str(c) or '/' in str(c)]
    
    for _, row in df_p.iterrows():
        # 근무조가 들어있는 열(보통 B열, index 1) 확인
        shift_raw = str(row.iloc[1]).strip().upper()
        # 'D', 'E', 'N'이 포함되어 있는지 확인 (D(1), E(2) 등 대응)
        shift = None
        if 'D' in shift_raw: shift = 'D'
        elif 'E' in shift_raw: shift = 'E'
        elif 'N' in shift_raw: shift = 'N'
        
        if not shift: continue 
        
        for col_name in date_cols:
            cell_content = str(row[col_name])
            if cell_content == 'nan' or not cell_content.strip(): continue
            
            # 셀 내부에 '병동'과 '이름' 분리
            # 줄바꿈(\n)이 없더라도 공백이나 숫자로 분리 시도
            lines = [l.strip() for l in cell_content.split('\n') if l.strip()]
            
            if len(lines) < 2:
                # 줄바꿈이 없는 경우: 숫자(병동)와 문자(이름) 분리 시도
                match = re.match(r'(\d+)\s*(.*)', cell_content)
                if match:
                    ward, name = match.groups()
                else: continue
            else:
                ward, name = lines[0], lines[1]
            
            try:
                # 컬럼 헤더에서 날짜 정보 추출 (예: "3/2~3/13")
                date_parts = re.findall(r'(\d+)/(\d+)|(\d+)', str(col_name))
                dates = []
                for p in date_parts:
                    if p[0]: dates.append((int(p[0]), int(p[1])))
                    elif p[2]: dates.append((dates[-1][0], int(p[2])))

                start_m, start_d = dates[0]
                end_m, end_d = dates[1]
                
                start_dt = datetime(year, start_m, start_d)
                end_dt = datetime(year, end_m, end_d)
                
                curr = start_dt
                while curr <= end_dt:
                    if curr.weekday() < 5: # 평일만
                        expanded_rows.append({
                            "날짜": curr.strftime('%Y-%m-%d'),
                            "근무": shift, "병동": ward, "성함": name
                        })
                    curr += timedelta(days=1)
            except: continue
            
    return pd.DataFrame(expanded_rows)

# --- [2. UI 및 메인 로직] ---
st.set_page_config(page_title="프라임 통합 분석기", layout="wide")
st.title("🏥 프라임 근무 정합성 자동 분석 시스템")

col_plan, col_actual = st.columns(2)

with col_plan:
    st.header("1️⃣ 배정표(계획)")
    file_p = st.file_uploader("주간 배정표 업로드", type="xlsx", key="p")
    df_p_final = pd.DataFrame()
    if file_p:
        # 데이터가 1행이 아닌 2~3행부터 시작할 수 있으므로 로드 후 확인
        df_p_raw = pd.read_excel(file_p)
        df_p_final = expand_plan_period_board(df_p_raw)
        
        if not df_p_final.empty:
            st.success(f"✅ 계획 데이터 {len(df_p_final)}건 추출 성공")
            st.dataframe(df_p_final, use_container_width=True)
        else:
            st.error("⚠️ 데이터를 읽지 못했습니다. 시트의 근무조(D/E) 위치와 날짜 헤더를 확인하세요.")

with col_actual:
    st.header("2️⃣ 실제 근무표(실제)")
    file_a = st.file_uploader("월간 근무표 업로드", type="xlsx", key="a")
    df_a_final = pd.DataFrame()
    if file_a:
        xl_a = pd.ExcelFile(file_a)
        sheet_a = st.selectbox("분석할 시트 선택", xl_a.sheet_names)
        df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
        
        try:
            base_month = int(re.sub(r'[^0-9]', '', sheet_a))
        except: base_month = 1
            
        start_col_idx = next((i for i, col in enumerate(df_a_raw.columns) if '1' in str(col)), 7)
        
        actual_rows = []
        for _, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip()
            if name == 'nan' or len(name) < 2: continue
            
            current_month, last_day = base_month, 0
            for col_idx in range(start_col_idx, len(df_a_raw.columns)):
                day_match = re.search(r'\d+', str(df_a_raw.columns[col_idx]))
                if day_match:
                    day = int(day_match.group())
                    if day < last_day:
                        current_month = current_month + 1 if current_month < 12 else 1
                    last_day = day
                    
                    shift, ward = parse_actual_work(row.iloc[col_idx])
                    if shift != "OFF":
                        date_str = f"2026-{str(current_month).zfill(2)}-{str(day).zfill(2)}"
                        actual_rows.append({"날짜": date_str, "근무": shift, "병동": ward, "성함": name})
        
        df_a_final = pd.DataFrame(actual_rows)
        st.success(f"✅ 실제 근무 추출 완료 ({len(df_a_final)}건)")
        st.dataframe(df_a_final, use_container_width=True)

# [분석 실행]
if not df_p_final.empty and not df_a_final.empty:
    if st.button("🚀 정합성 분석 시작"):
        df_merge = pd.merge(df_a_final, df_p_final, on=["날짜", "성함"], how="outer", suffixes=("_실제", "_계획"))
        def check_diff(row):
            if pd.isna(row['병동_계획']): return "계획 외 지원"
            if pd.isna(row['병동_실제']): return "계획 미이행"
            if str(row['병동_실제']) != str(row['병동_계획']): return "병동 불일치"
            return "정상"
        df_merge['분석결과'] = df_merge.apply(check_diff, axis=1)
        st.dataframe(df_merge, use_container_width=True)
