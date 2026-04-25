import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [1. 핵심 파싱 함수] ---
def parse_actual_work(cell_value):
    """P-D4/116 형식을 (근무: D, 병동: 116)으로 분리"""
    val = str(cell_value).strip()
    off_keywords = ['건', '필', 'ET', '/', 'nan', 'None', '']
    if not val.startswith('P-') and (any(k in val for k in off_keywords) or val == ''):
        return "OFF", None
    match = re.search(r'P-([a-zA-Z])\d*/(\d+)', val)
    if match:
        return match.group(1).upper(), match.group(2)
    return "OFF", None

def expand_plan_period_board(df_p, year=2026):
    """배정표(계획): 3/30~4/10 같은 교차 월 자동 인식 확장"""
    expanded_rows = []
    date_cols = [c for c in df_p.columns if '~' in str(c)]
    
    for _, row in df_p.iterrows():
        shift = str(row.iloc[1]).strip().upper()
        if shift not in ['D', 'E', 'N']: continue 
        
        for col_name in date_cols:
            cell_content = str(row[col_name])
            if cell_content == 'nan' or not cell_content.strip(): continue
            
            lines = cell_content.split('\n')
            if len(lines) < 2: continue
            ward, name = lines[0].strip(), lines[1].strip()
            
            try:
                # 기간 추출 (예: "3/30~4/10")
                date_parts = re.findall(r'(\d+)/(\d+)|(\d+)', col_name)
                dates = []
                for p in date_parts:
                    if p[0]: dates.append((int(p[0]), int(p[1])))
                    elif p[2]: dates.append((dates[-1][0], int(p[2])))

                start_m, start_d = dates[0]
                end_m, end_d = dates[1]
                
                # 시작일과 종료일 객체 생성 (월이 다를 경우 자동 처리)
                start_dt = datetime(year, start_m, start_d)
                # 종료 월이 시작 월보다 작으면 (예: 12월~1월) 연도 증가 로직은 필요시 추가
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

# --- [2. UI 설정 (사이드바 제거)] ---
st.set_page_config(page_title="프라임 통합 분석기", layout="wide")
st.title("🏥 프라임 근무 정합성 자동 분석 시스템")
st.info("💡 사이드바 설정 없이, 업로드된 파일의 시트 이름과 데이터를 기반으로 월을 자동 인식합니다.")

col_plan, col_actual = st.columns(2)

# --- [3. 배정표(Plan) 처리] ---
with col_plan:
    st.header("1️⃣ 배정표(계획)")
    file_p = st.file_uploader("주간 배정표 업로드", type="xlsx", key="p")
    df_p_final = pd.DataFrame()
    if file_p:
        df_p_raw = pd.read_excel(file_p)
        df_p_final = expand_plan_period_board(df_p_raw)
        st.success(f"✅ 계획 데이터 추출 완료 ({len(df_p_final)}건)")
        st.dataframe(df_p_final, use_container_width=True)

# --- [4. 실제 근무표(Actual) 처리 - 월 자동 전환] ---
with col_actual:
    st.header("2️⃣ 실제 근무표(실제)")
    file_a = st.file_uploader("월간 근무표 업로드", type="xlsx", key="a")
    df_a_final = pd.DataFrame()
    if file_a:
        xl_a = pd.ExcelFile(file_a)
        sheet_a = st.selectbox("분석할 시트 선택", xl_a.sheet_names)
        df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
        
        # [자동 월 인식] 시트명에서 시작 월 추출 (예: "3월 스케줄" -> 3)
        try:
            base_month = int(re.sub(r'[^0-9]', '', sheet_a))
        except:
            base_month = 1 # 숫자가 없으면 1월로 기본값
            
        start_col_idx = next((i for i, col in enumerate(df_a_raw.columns) if '1' in str(col)), 7)
        
        actual_rows = []
        for _, row in df_a_raw.iterrows():
            name = str(row.iloc[2]).strip()
            if name == 'nan' or len(name) < 2: continue
            
            current_month = base_month
            last_day = 0
            
            for col_idx in range(start_col_idx, len(df_a_raw.columns)):
                day_match = re.search(r'\d+', str(df_a_raw.columns[col_idx]))
                if day_match:
                    day = int(day_match.group())
                    
                    # 날짜가 작아지면 (31일 -> 1일) 다음 달로 인식
                    if day < last_day:
                        current_month += 1
                        if current_month > 12: current_month = 1
                    last_day = day
                    
                    shift, ward = parse_actual_work(row.iloc[col_idx])
                    if shift != "OFF":
                        # 2026년 고정 (필요시 연도 추출 로직 추가 가능)
                        date_str = f"2026-{str(current_month).zfill(2)}-{str(day).zfill(2)}"
                        actual_rows.append({"날짜": date_str, "근무": shift, "병동": ward, "성함": name})
        
        df_a_final = pd.DataFrame(actual_rows)
        st.success(f"✅ 실제 근무 데이터 추출 완료 ({len(df_a_final)}건)")
        st.dataframe(df_a_final, use_container_width=True)

# --- [5. 최종 정합성 분석] ---
st.markdown("---")
if not df_p_final.empty and not df_a_final.empty:
    if st.button("🚀 계획 vs 실제 정합성 분석 시작"):
        # 날짜와 성함을 기준으로 두 데이터 병합
        df_merge = pd.merge(df_a_final, df_p_final, on=["날짜", "성함"], how="outer", suffixes=("_실제", "_계획"))
        
        # 불일치 분석 결과 생성
        def check_diff(row):
            if pd.isna(row['병동_계획']): return "계획 외 지원"
            if pd.isna(row['병동_실제']): return "계획 미이행"
            if str(row['병동_실제']) != str(row['병동_계획']): return "병동 불일치"
            return "정상"

        df_merge['분석결과'] = df_merge.apply(check_diff, axis=1)
        
        st.subheader("🔍 최종 비교 분석 리스트")
        st.dataframe(df_merge, use_container_width=True)
        
        # 통계 요약
        st.subheader("📊 항목별 통계")
        st.write(df_merge['분석결과'].value_counts())
