import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. 날짜 및 데이터 정제 엔진 ---

def expand_date_range(date_str, year=2026):
    """'3/30~4/10' 같은 텍스트를 실제 날짜 리스트로 변환 """
    try:
        date_str = date_str.replace('일', '').replace('평일', '').strip()
        start_part, end_part = date_str.split('~')
        
        # 시작 날짜 추출
        s_match = re.findall(r'\d+', start_part)
        s_month, s_day = int(s_match[0]), int(s_match[1])
        start_date = datetime(year, s_month, s_day)
        
        # 종료 날짜 추출
        e_match = re.findall(r'\d+', end_part)
        if len(e_match) == 2: # '4/10' 형태
            e_month, e_day = int(e_match[0]), int(e_match[1])
        else: # '24' 형태 (같은 달)
            e_month, e_day = s_month, int(e_match[0])
        end_date = datetime(year, e_month, e_day)
        
        return [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    except:
        return []

def get_unified_plan(uploaded_file):
    """계획표 정제: 날짜별 1행 데이터 생성 """
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    plan_list = []

    for sheet_name, df in all_sheets.items():
        date_cols = [i for i, col in enumerate(df.columns) if '~' in str(col)]
        shift_col = next((i for i, col in enumerate(df.columns) if '근무조' in str(col)), 1)
        
        current_shift = "D"
        for idx, row in df.iterrows():
            if 'D' in str(row[shift_col]): current_shift = "D"
            elif 'E' in str(row[shift_col]): current_shift = "E"
            
            for col_idx in date_cols:
                cell = str(row[col_idx])
                # '병동\n이름' 추출 
                match = re.search(r'(\d+)\s*\n\s*([가-힣]+)', cell)
                if match:
                    ward, name = match.group(1), match.group(2)
                    dates = expand_date_range(df.columns[col_idx])
                    for d in dates:
                        plan_list.append({
                            '성함': name,
                            '날짜': d,
                            '계획병동': str(int(ward)),
                            '근무조': current_shift
                        })
    return pd.DataFrame(plan_list)

def get_unified_actual(uploaded_file):
    """실제 근무표 정제: P- 코드만 추출하여 1행 데이터 생성 """
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    actual_list = []

    for sheet_name, df in all_sheets.items():
        month_match = re.findall(r'\d+', sheet_name)
        if not month_match: continue
        month = int(month_match[0])
        
        name_col = next((c for c in df.columns if '명' in str(c)), '명') [cite: 1]
        day_cols = [c for c in df.columns if '일' in str(c)]
        
        for _, row in df.iterrows():
            name = row[name_col]
            if pd.isna(name): continue
            
            for day_col in day_cols:
                day_match = re.findall(r'\d+', day_col)
                if not day_match: continue
                day = int(day_match[0])
                code = str(row[day_col])
                
                # 'P-' 근무만 추출 (건, 필, ET 등 제외)
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code) [cite: 1]
                    if ward_match:
                        actual_list.append({
                            '성함': name,
                            '날짜': datetime(2026, month, day),
                            '실제병동': str(int(ward_match.group(1)))
                        })
    return pd.DataFrame(actual_list)

# --- 2. Streamlit UI 및 분석 실행 ---

st.set_page_config(page_title="NSS 스마트 분석", layout="wide")
st.title("🏥 프라임 간호사 통합 실적 분석 시스템")

st.info("💡 계획표(Plan)와 실제 근무표(Actual)를 업로드하면 날짜별로 비교 분석합니다.")

col1, col2 = st.columns(2)
with col1:
    uploaded_p = st.file_uploader("1. 대기병동 배정표(Plan) 업로드", type="xlsx")
with col2:
    uploaded_a = st.file_uploader("2. 실제 근무스케줄표(Actual) 업로드", type="xlsx")

if uploaded_p and uploaded_a:
    try:
        # 데이터 처리
        with st.spinner('데이터를 매칭 중입니다...'):
            df_p = get_unified_plan(uploaded_p)
            df_a = get_unified_actual(uploaded_a)
            
            # 병합 (성함과 날짜 기준)
            merged = pd.merge(df_a, df_p, on=['성함', '날짜'], how='left')
            
            # 구분 로직 적용
            def classify(row):
                if pd.isna(row['계획병동']): return "기타"
                return "지원(순환)" if row['실제병동'] == row['계획병동'] else "결원대체"
            
            merged['상태'] = merged.apply(classify, axis=1)
            merged['날짜'] = merged['날짜'].dt.strftime('%Y-%m-%d')

        # 분석 결과 리포트
        st.header("📊 분석 요약 리포트")
        
        # 1. 집계 표
        summary = merged[merged['상태'] != "기타"].groupby('성함')['상태'].value_counts().unstack().fillna(0)
        st.subheader("✅ 간호사별 최종 실적")
        st.table(summary.astype(int))

        # 2. 상세 내역 (검색/필터 가능)
        st.subheader("📝 날짜별 상세 비교 내역")
        target_nurse = st.selectbox("성함을 선택하여 상세 내역을 확인하세요", ["전체"] + list(merged['성함'].unique()))
        
        if target_nurse == "전체":
            st.dataframe(merged[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']], use_container_width=True)
        else:
            filtered = merged[merged['성함'] == target_nurse]
            st.dataframe(filtered[['날짜', '근무조', '계획병동', '실제병동', '상태']], use_container_width=True)

        # 3. 다운로드 버튼
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            merged.to_excel(writer, index=False, sheet_name='분석결과')
        st.download_button("📥 전체 분석 결과 다운로드 (Excel)", output.getvalue(), "NSS_Analysis_Result.xlsx")

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
