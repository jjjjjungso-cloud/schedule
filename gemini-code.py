import streamlit as st
import pandas as pd
import re
from io import BytesIO

# --- 1. 유의미한 데이터만 뽑아내는 핵심 정제 함수 (보강됨) ---

def refined_plan_cleaning(uploaded_file):
    """제목줄이 복잡한 엑셀에서 '근무조'와 '날짜' 열을 자동으로 감지합니다."""
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    refined_results = []

    for sheet_name, df in all_sheets.items():
        # [수정] 엑셀의 모든 셀을 뒤져서 '근무조' 글자가 있는 열 번호 찾기
        shift_col_idx = -1
        for i in range(min(10, len(df))): # 상위 10행 스캔
            row_vals = df.iloc[i].astype(str).tolist()
            for j, val in enumerate(row_vals):
                if '근무조' in val:
                    shift_col_idx = j
                    break
            if shift_col_idx != -1: break
        
        if shift_col_idx == -1: shift_col_idx = 1 # 못 찾으면 기본값 B열
        
        # [수정] 날짜 구간 열 찾기 (헤더와 데이터 상단 모두 검색)
        date_cols = []
        for j, col in enumerate(df.columns):
            if '~' in str(col): date_cols.append(j)
        if not date_cols:
            for i in range(min(5, len(df))):
                row_vals = df.iloc[i].astype(str).tolist()
                date_cols = [j for j, val in enumerate(row_vals) if '~' in val]
                if date_cols: break

        current_shift = "D" 

        for idx, row in df.iterrows():
            # [수정] iloc를 사용하여 열 이름이 아닌 번호로 안전하게 접근 (KeyError 방지)
            shift_val = str(row.iloc[shift_col_idx]).strip()
            if 'D' in shift_val: current_shift = "D"
            elif 'E' in shift_val: current_shift = "E"
            
            for col_idx in date_cols:
                cell_val = str(row.iloc[col_idx])
                # 병동번호\n성함 추출
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell_val)
                
                if match:
                    # 날짜 구간 텍스트 가져오기
                    date_label = str(df.columns[col_idx]) if '~' in str(df.columns[col_idx]) else "구간미상"
                    
                    refined_results.append({
                        "해당월": sheet_name,
                        "날짜구간": date_label,
                        "근무조": current_shift,
                        "성함": match.group(2),
                        "계획병동": str(int(match.group(1)))
                    })
                    
    return pd.DataFrame(refined_results)

def clean_actual_schedule(uploaded_file):
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    all_actual = []

    for sheet_name, df in all_sheets.items():
        # '명' 컬럼 위치 자동 감지
        name_col_idx = -1
        for i, col in enumerate(df.columns):
            if '명' in str(col): name_col_idx = i; break
        if name_col_idx == -1: name_col_idx = 2 # 기본값 C열
        
        # '일'이 포함된 열(날짜열) 찾기
        day_cols_idx = [i for i, col in enumerate(df.columns) if '일' in str(col)]
        
        for idx, row in df.iterrows():
            name = str(row.iloc[name_col_idx]).strip()
            if name in ['nan', '명', '성명', '']: continue
            
            for d_idx in day_cols_idx:
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        all_actual.append({
                            "성함": name,
                            "실제병동": str(int(ward_match.group(1))),
                            "월": sheet_name
                        })
    return pd.DataFrame(all_actual)

# --- 2. 스트림릿 UI 구성 (이전과 동일하게 유지하되 로직 보강) ---

st.set_page_config(page_title="프라임 배정 시스템", layout="wide")
st.title("🏥 프라임 간호사 스마트 순환 배정 시스템")

st.header("Step 1. 과거 데이터 업로드")
c1, c2 = st.columns(2)
with c1: up_p = st.file_uploader("1. 계획표 업로드 (Excel)", type="xlsx")
with c2: up_a = st.file_uploader("2. 실제 근무표 업로드 (Excel)", type="xlsx")

if up_p and up_a:
    try:
        with st.spinner('데이터를 정밀 분석 중입니다...'):
            df_plan = refined_plan_cleaning(up_p)
            df_actual = clean_actual_schedule(up_a)
        
        if df_plan.empty or df_actual.empty:
            st.warning("데이터를 읽어오지 못했습니다. 파일 양식을 확인해주세요.")
        else:
            st.success("✅ 데이터를 성공적으로 추출했습니다!")

            st.header("Step 2. 지원 vs 결원 대체 분석")
            summary = []
            for name in df_plan['성함'].unique():
                p_wards = set(df_plan[df_plan['성함'] == name]['계획병동'])
                a_wards = set(df_actual[df_actual['성함'] == name]['실제병동'])
                
                support = p_wards.intersection(a_wards)
                substitute = a_wards.difference(p_wards)
                
                summary.append({
                    "성함": name,
                    "지원(순환) 병동": ", ".join(sorted(list(support))),
                    "결원 대체(숙련도) 병동": ", ".join(sorted(list(substitute))),
                    "결원 대체 횟수": len(substitute)
                })
            
            st.table(pd.DataFrame(summary).sort_values('결원 대체 횟수', ascending=False))
            
    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
