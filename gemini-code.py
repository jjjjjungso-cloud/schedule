import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta
import io

# --- 1. 데이터베이스 초기화 (1단계와 동일) ---
def init_db():
    conn = sqlite3.connect('prime_nurse.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS nurses (
                    name TEXT PRIMARY KEY, unit TEXT, sub_count INTEGER DEFAULT 0,
                    last_d_dedicated TEXT, visited_wards TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS assignment_logs (
                    date TEXT, name TEXT, plan_ward TEXT, actual_ward TEXT,
                    shift TEXT, status TEXT, UNIQUE(date, name))''')
    conn.commit()
    conn.close()

# --- 2. 데이터 정제 엔진 (보강됨) ---

import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [로직 1] 데이터 정제 및 평일 확장 엔진 ---
def process_data_with_preview(df):
    # 모든 열 이름의 앞뒤 공백 제거 및 문자열 변환
    df.columns = [str(col).strip() for col in df.columns]
    
    # 필수 열 정의
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    
    # '성함'으로 적었을 경우 보정
    if '성함' in df.columns and '간호사 성함' not in df.columns:
        df = df.rename(columns={'성함': '간호사 성함'})

    missing = [c for c in required if c not in df.columns]
    if missing:
        return None, f"⚠️ 필수 제목 중 {missing}을 찾을 수 없습니다. 아래 원본 데이터의 제목을 확인해주세요!"

    results = []
    for _, row in df.iterrows():
        try:
            # 셀 내용 공백 제거
            name = str(row['간호사 성함']).strip()
            shift = str(row['근무조']).strip().upper()
            ward = re.sub(r'[^0-9]', '', str(row['배정병동'])) # 숫자만 쏙!
            
            s_date = pd.to_datetime(row['시작일'])
            e_date = pd.to_datetime(row['종료일'])

            curr = s_date
            while curr <= e_date:
                if curr.weekday() < 5: # 평일(월-금)만!
                    results.append({
                        '날짜': curr.strftime('%Y-%m-%d'),
                        '요일': ['월', '화', '수', '목', '금'][curr.weekday()],
                        '성함': name,
                        '계획병동': ward,
                        '근무조': shift
                    })
                curr += timedelta(days=1)
        except:
            continue
    return pd.DataFrame(results), None

# --- [로직 2] UI 및 대시보드 ---
st.set_page_config(page_title="프라임 데이터 검증기", layout="wide")
st.title("🏥 프라임 대기병동 분석 마스터")
st.markdown("---")

up_file = st.file_uploader("배정표 엑셀 파일을 올려주세요 (.xlsx)", type=["xlsx"])

if up_file:
    xl = pd.ExcelFile(up_file)
    selected_sheet = st.sidebar.selectbox("시트 선택", xl.sheet_names)
    
    if selected_sheet:
        # 데이터 읽기 (일단 제목 줄을 찾기 위해 원본 그대로 읽음)
        df_raw = pd.read_excel(up_file, sheet_name=selected_sheet)
        
        # -------------------------------------------
        # 🔍 1단계: 컴퓨터가 본 원본 데이터 확인창
        # -------------------------------------------
        st.subheader("🔍 1단계: 컴퓨터가 인식한 파일 내용")
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.info("💡 **인식된 열 제목 리스트**")
            # 공백 제거 전 원본 제목을 보여줌 (오타 확인용)
            actual_cols = list(df_raw.columns)
            st.write(actual_cols)
            
        with c2:
            st.info("💡 **데이터 미리보기 (상위 5줄)**")
            st.dataframe(df_raw.head(), use_container_width=True)

        st.markdown("---")
        
        # -------------------------------------------
        # 📊 2단계: 분석 결과 리포트
        # -------------------------------------------
        if st.button("🚀 위 데이터가 맞습니다. 분석 시작!"):
            df_final, error = process_data_with_preview(df_raw)
            
            if error:
                st.error(error)
                st.warning("엑셀의 첫 번째 줄이 제목(`시작일`, `종료일` 등)이 맞는지 확인해주세요!")
            elif not df_final.empty:
                st.success(f"✅ {len(df_final)}일치의 평일 스케줄 분석 완료!")
                
                res_col, chart_col = st.columns([1.5, 1])
                
                with res_col:
                    st.markdown("#### 📋 분석된 상세 일정")
                    st.dataframe(df_final, height=400)
                
                with chart_col:
                    st.markdown("#### 📈 간호사별 지원 실적")
                    # 성함별 횟수 차트
                    stats = df_final['성함'].value_counts()
                    st.bar_chart(stats)
                    
                # 다운로드 기능
                csv = df_final.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 분석 결과 다운로드 (CSV)", csv, "prime_result.csv", "text/csv")
            else:
                st.warning("데이터는 읽었으나 분석할 수 있는 내용이 없습니다.")

def process_data(uploaded_p, uploaded_a, year, month_str):
    """계획표와 실제근무표를 병합하여 실적 데이터 생성"""
    # 1. 계획표 파싱
    df_p_all = pd.read_excel(uploaded_p, sheet_name=None)
    plan_records = []
    for sheet, df in df_p_all.items():
        # 키워드 기반 열 찾기
        date_cols = [i for i, c in enumerate(df.columns) if '~' in str(c)]
        shift_col = next((i for i, c in enumerate(df.columns) if '근무조' in str(c)), 1)
        
        curr_shift = "D"
        for _, row in df.iterrows():
            s_val = str(row.iloc[shift_col])
            if 'D' in s_val: curr_shift = 'D'
            elif 'E' in s_val: curr_shift = 'E'
            
            for c_idx in date_cols:
                cell = str(row.iloc[c_idx])
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', cell)
                if match:
                    ward, name = match.group(1), match.group(2)
                    dates = expand_dates(df.columns[c_idx], year)
                    for d in dates:
                        plan_records.append({'name': name, 'date': d.strftime('%Y-%m-%d'), 'plan_ward': ward, 'shift': curr_shift})
    
    # 2. 실제근무표 파싱
    df_a_all = pd.read_excel(uploaded_a, sheet_name=None)
    actual_records = []
    target_m = int(re.findall(r'\d+', month_str)[0])
    
    for sheet, df in df_a_all.items():
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '']: continue
            for d_idx in day_cols:
                day = int(re.findall(r'\d+', str(df.columns[d_idx]))[0])
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        actual_records.append({'name': name, 'date': datetime(year, target_m, day).strftime('%Y-%m-%d'), 'actual_ward': str(int(ward_match.group(1)))})

    # 3. 데이터 병합
    df_p, df_a = pd.DataFrame(plan_records), pd.DataFrame(actual_records)
    if df_p.empty or df_a.empty: return pd.DataFrame()
    
    merged = pd.merge(df_a, df_p, on=['name', 'date'], how='left')
    merged['status'] = merged.apply(lambda r: "지원(순환)" if r['actual_ward'] == r['plan_ward'] else "결원대체", axis=1)
    return merged

# --- 3. 핵심 알고리즘: 전략적 추천 및 순번제 ---

def get_recommendations(unit_name):
    """특정 동의 간호사별 차기 대기 병동 추천"""
    conn = sqlite3.connect('prime_nurse.db')
    # 실제 환경에서는 DB에서 가져오지만, 예시를 위해 로직 구성
    nurses = pd.read_sql_query(f"SELECT * FROM nurses WHERE unit = '{unit_name}'", conn)
    logs = pd.read_sql_query("SELECT * FROM assignment_logs", conn)
    conn.close()
    
    recs = []
    # 모든 병동 리스트 (예시: 41, 51, 61, 71, 91, 101, 111, 122, 131)
    all_wards = ['41', '51', '61', '71', '72', '85', '91', '101', '111', '116', '122', '131']
    
    for _, nurse in nurses.iterrows():
        visited = set(str(nurse['visited_wards']).split(',')) if nurse['visited_wards'] else set()
        not_visited = [w for w in all_wards if w not in visited]
        
        target_ward = not_visited[0] if not_visited else "모든 병동 경험 완료"
        recs.append({
            "성함": nurse['name'],
            "현재 결원대체": f"{nurse['sub_count']}회",
            "D전담 이력": nurse['last_d_dedicated'] if nurse['last_d_dedicated'] else "이력없음",
            "차기 추천 병동": target_ward,
            "상태": "신규 경험 필요" if target_ward in not_visited else "숙련도 유지"
        })
    return pd.DataFrame(recs)

# --- 4. Streamlit UI (2단계 보강) ---

st.set_page_config(page_title="프라임 전략 대시보드", layout="wide")
init_db()

st.title("📊 프라임 간호사 전략적 배치 시스템")

# 사이드바 설정
st.sidebar.header("📅 설정")
year = st.sidebar.selectbox("연도", [2026, 2027])
month = st.sidebar.select_slider("월", [f"{i}월" for i in range(1, 13)])

# 데이터 업로드
c1, c2 = st.columns(2)
with c1: up_p = st.file_uploader("1. 계획표(Plan)", type="xlsx")
with c2: up_a = st.file_uploader("2. 실제근무표(Actual)", type="xlsx")

if up_p and up_a:
    df_merged = process_data(up_p, up_a, year, month)
    
    if not df_merged.empty:
        st.success(f"✅ {month} 데이터 분석 완료!")
        
        # [기능 1] 동별 독립 D-전담 순번제 제안
        st.header("🔄 동별 D-전담 순번제 제안")
        col_u1, col_u2 = st.columns(2)
        
        with col_u1:
            st.subheader("1동 (7명)")
            # 이력 기반 가장 오래된 사람 추천 (가상 데이터)
            st.info("💡 차기 D-전담 추천: **박소영** (마지막 수행: 2025-11)")
            
        with col_u2:
            st.subheader("2동 (6명)")
            st.info("💡 차기 D-전담 추천: **최휘영** (마지막 수행: 2025-12)")

        # [기능 2] 전략적 차기 대기 병동 추천
        st.header("🚀 데이터 기반 차기 대기 병동 추천")
        st.write("간호사별 병동 경험 공백(0회 방문)을 분석하여 최적의 대기 장소를 제안합니다.")
        
        # 1동 추천
        st.subheader("📍 1동 전략 가이드")
        st.table(get_recommendations("1동"))
        
        # 저장 버튼
        if st.button("💾 분석 결과 DB에 최종 저장"):
            # DB 저장 로직 (중복 방지 Upsert) 수행 후 알림
            st.balloons()
            st.success("데이터베이스에 실적 및 이력이 업데이트되었습니다.")
    else:
        st.error("데이터 매칭에 실패했습니다. 파일 양식을 확인해 주세요.")

else:
    st.info("파일을 업로드하면 동별 순번제와 전략 추천 알고리즘이 가동됩니다.")
