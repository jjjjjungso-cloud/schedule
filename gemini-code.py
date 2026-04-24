import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. 유틸리티 및 정제 엔진 ---

def expand_date_range_with_month(date_str, year=2026):
    """'3/30~4/10' 문자열을 날짜 리스트로 풀고, 시작일 기준의 '분석월' 반환"""
    try:
        date_str = str(date_str).replace('일', '').replace('평일', '').strip()
        if '~' not in date_str: return [], None
        
        start_part, end_part = date_str.split('~')
        s_match = re.findall(r'\d+', start_part)
        s_month, s_day = int(s_match[0]), int(s_match[1])
        start_date = datetime(year, s_month, s_day)
        
        # 소영님 규칙: 구간의 시작일이 속한 월을 '분석월'로 지정
        display_month = f"{year}년 {s_month}월"
        
        e_match = re.findall(r'\d+', end_part)
        if len(e_match) == 2:
            e_month, e_day = int(e_match[0]), int(e_match[1])
        else:
            e_month, e_day = s_month, int(e_match[0])
        end_date = datetime(year, e_month, e_day)
        
        dates = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        return dates, display_month
    except:
        return [], None

def get_dashboard_data(uploaded_p, uploaded_a):
    """계획표와 실제근무표를 읽어 통합 분석 데이터 생성"""
    
    # 1. 계획표(Plan) 정제
    all_p_sheets = pd.read_excel(uploaded_p, sheet_name=None, engine='openpyxl')
    plan_data = []
    
    for sheet_name, df in all_p_sheets.items():
        # 유의미한 날짜 열 찾기
        date_cols = [i for i, col in enumerate(df.columns) if '~' in str(col)]
        
        # [수정됨] '근무조' 열 위치를 더 유연하게 찾기 (에러 방지 로직)
        shift_col_idx = -1
        for i, col in enumerate(df.columns):
            if '근무조' in str(col):
                shift_col_idx = i
                break
        if shift_col_idx == -1: # 제목줄에 없으면 상위 5줄 검색
            for i in range(min(5, len(df))):
                row_vals = df.iloc[i].astype(str).tolist()
                for j, val in enumerate(row_vals):
                    if '근무조' in val:
                        shift_col_idx = j
                        break
                if shift_col_idx != -1: break
        if shift_col_idx == -1: shift_col_idx = 1 # 기본값 B열
        
        for idx, row in df.iterrows():
            # D4, D8 등 숫자가 포함된 D근무도 모두 D로 통합 인식
            shift_val = str(row.iloc[shift_col_idx])
            if 'D' in shift_val: curr_shift = "D"
            elif 'E' in shift_val: curr_shift = "E"
            else: continue # D나 E가 없으면 스킵
            
            for col_idx in date_cols:
                cell = str(row.iloc[col_idx])
                # '병동\n이름' 패턴 추출
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell)
                if match:
                    ward, name = match.group(1), match.group(2)
                    dates, target_month = expand_date_range_with_month(df.columns[col_idx])
                    if target_month:
                        for d in dates:
                            plan_data.append({
                                '성함': name, '날짜': d, '계획병동': str(int(ward)), 
                                '근무조': curr_shift, '분석월': target_month
                            })
    df_p = pd.DataFrame(plan_data)

    # 2. 실제 근무표(Actual) 정제
    all_a_sheets = pd.read_excel(uploaded_a, sheet_name=None, engine='openpyxl')
    actual_data = []
    
    for sheet_name, df in all_a_sheets.items():
        # 시트명에서 월 추출 (예: '3월')
        m_match = re.findall(r'\d+', sheet_name)
        month = int(m_match[0]) if m_match else 3
        
        # '명' 또는 '성명' 컬럼 찾기
        name_col_idx = -1
        for i, col in enumerate(df.columns):
            if '명' in str(col): name_col_idx = i; break
        if name_col_idx == -1: # 제목줄에 없으면 첫 줄 검색
            row0 = df.iloc[0].astype(str).tolist()
            for j, val in enumerate(row0):
                if '명' in val: name_col_idx = j; break
        
        day_cols = [i for i, col in enumerate(df.columns) if '일' in str(col)]
        
        for idx, row in df.iterrows():
            name = str(row.iloc[name_col_idx]).strip()
            if not name or name == 'nan' or name == '명': continue
            
            for d_idx in day_cols:
                day_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not day_match: continue
                day = int(day_match[0])
                code = str(row.iloc[d_idx])
                
                # 'P-'로 시작하는 근무만 인정 (건, 필, ET, / 등은 제외)
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        actual_data.append({
                            '성함': name, 
                            '날짜': datetime(2026, month, day), 
                            '실제병동': str(int(ward_match.group(1)))
                        })
    df_a = pd.DataFrame(actual_data)

    # 3. 데이터 통합 및 상태 판별
    merged = pd.merge(df_a, df_p, on=['성함', '날짜'], how='left')
    merged = merged.dropna(subset=['분석월']) # 계획 구간 외 날짜 제외
    
    def classify(row):
        # 계획 병동과 실제 병동이 일치하면 지원, 아니면 결원대체
        return "지원(순환)" if row['실제병동'] == row['계획병동'] else "결원대체"
    
    merged['상태'] = merged.apply(classify, axis=1)
    return merged

# --- 2. Streamlit 대시보드 UI ---

st.set_page_config(page_title="프라임 스마트 대시보드", layout="wide")
st.title("🏥 프라임 간호사 통합 운영 대시보드")
st.markdown("##### 계획(Plan)과 실제(Actual) 데이터를 비교하여 결원대체 현황과 형평성을 분석합니다.")

col1, col2 = st.columns(2)
with col1:
    up_p = st.file_uploader("1. 대기병동 배정표(Plan) 엑셀 업로드", type="xlsx")
with col2:
    up_a = st.file_uploader("2. 실제 근무스케줄표(Actual) 엑셀 업로드", type="xlsx")

if up_p and up_a:
    try:
        with st.spinner('데이터를 통합 분석 중입니다...'):
            data = get_dashboard_data(up_p, up_a)
            
        months = sorted(data['분석월'].unique())
        tabs = st.tabs(months) # 월별 탭 생성
        
        for i, month_tab in enumerate(tabs):
            with month_tab:
                m_data = data[data['분석월'] == months[i]]
                
                # [형평성 중심 집계]
                st.subheader(f"⚖️ {months[i]} 배정 형평성 리포트")
                st.info("💡 **배정 가이드:** 결원대체 횟수가 적은 사람이 표의 상단에 위치합니다. 다음 결원 발생 시 상위 인원을 우선 고려하세요.")
                
                summary = m_data.groupby('성함').apply(lambda x: pd.Series({
                    '결원대체 횟수': (x['상태'] == '결원대체').sum(),
                    '지원(순환) 횟수': (x['상태'] == '지원(순환)').sum(),
                    '결원대체 병동 (날짜)': ", ".join([f"{row['실제병동']}({row['날짜'].strftime('%m/%d')})" 
                                               for _, row in x[x['상태'] == '결원대체'].iterrows()]),
                    '지원 병동 이력': ", ".join(sorted(set(x[x['상태'] == '지원(순환)']['실제병동'])))
                })).reset_index()
                
                # 형평성 로직: 결원대체 횟수가 적은 순으로 정렬
                summary = summary.sort_values(by=['결원대체 횟수', '지원(순환) 횟수'])
                st.table(summary)
                
                # 상세 내역
                with st.expander(f"🔍 {months[i]} 일자별 상세 매칭 내역 확인"):
                    display_df = m_data[['날짜', '성함', '근무조', '계획병동', '실제병동', '상태']].copy()
                    display_df['날짜'] = display_df['날짜'].dt.strftime('%Y-%m-%d')
                    st.dataframe(display_df.sort_values(['성함', '날짜']), use_container_width=True)

        # 엑셀 다운로드 기능
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            data.to_excel(writer, index=False, sheet_name='통합분석결과')
        st.download_button("📥 전체 분석 결과 엑셀 다운로드", output.getvalue(), "NSS_Integrated_Analysis.xlsx")

    except Exception as e:
        st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")
        st.info("팁: 엑셀 파일의 시트명(예: 3월, 4월)과 '근무조', '명' 등의 열 이름이 포함되어 있는지 확인해주세요.")
