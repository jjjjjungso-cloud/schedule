import streamlit as st
import pandas as pd

# --- UI 설정 ---
st.set_page_config(page_title="프라임 데이터 입력 검증", layout="wide")
st.title("🏥 프라임 데이터 입력 및 정합성 검증")
st.markdown("""
이 단계에서는 **배정표(계획)**와 **근무표(실제)**를 각각 업로드하고, 
컴퓨터가 각 열의 제목과 데이터를 제대로 읽어오는지 확인합니다.
""")

# --- 사이드바: 연도 및 월 설정 ---
st.sidebar.header("📅 분석 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("대상 월", [f"{i}월" for i in range(1, 13)], index=3) # 기본 4월

st.markdown("---")

# --- 영역 나누기 (좌: 배정표 / 우: 근무표) ---
col_plan, col_actual = st.columns(2)

# [1. 배정표(Plan) 영역]
with col_plan:
    st.header("1️⃣ 배정표(계획) 업로드")
    file_p = st.file_uploader("주간 배정표(.xlsx)를 선택하세요", type="xlsx", key="plan_up")
    
    if file_p:
        xl_p = pd.ExcelFile(file_p)
        sheet_p = st.selectbox("분석할 시트 선택 (계획)", xl_p.sheet_names, key="plan_sheet")
        
        # 데이터 읽기
        df_p_raw = pd.read_excel(file_p, sheet_name=sheet_p)
        
        st.success(f"✅ '{sheet_p}' 시트를 읽어왔습니다.")
        
        with st.expander("🔍 배정표 인식 상태 확인"):
            st.info("**컴퓨터가 찾은 제목(Columns):**")
            st.write(list(df_p_raw.columns))
            
            st.info("**상위 5행 데이터:**")
            st.dataframe(df_p_raw.head(), use_container_width=True)
            
            # 필수 키워드 체크
            required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
            found = [c for c in required if c in df_p_raw.columns]
            missing = set(required) - set(found)
            
            if not missing:
                st.write("✔️ 필수 항목이 모두 확인되었습니다.")
            else:
                st.warning(f"⚠️ 다음 항목을 찾을 수 없습니다: {list(missing)}")

# [2. 근무표(Actual) 영역]
with col_actual:
    st.header("2️⃣ 실제 근무표(Actual) 업로드")
    file_a = st.file_uploader("월간 근무표(.xlsx)를 선택하세요", type="xlsx", key="actual_up")
    
    if file_a:
        xl_a = pd.ExcelFile(file_a)
        sheet_a = st.selectbox("분석할 시트 선택 (실제)", xl_a.sheet_names, key="actual_sheet")
        
        # 실제 근무표는 제목줄이 보통 2~3행에 있을 수 있으므로 확인용으로 읽기
        df_a_raw = pd.read_excel(file_a, sheet_name=sheet_a)
        
        st.success(f"✅ '{sheet_a}' 시트를 읽어왔습니다.")
        
        with st.expander("🔍 근무표 인식 상태 확인"):
            st.info("**컴퓨터가 찾은 제목(Columns):**")
            st.write(list(df_a_raw.columns))
            
            st.info("**상위 5행 데이터:**")
            st.dataframe(df_a_raw.head(), use_container_width=True)
            
            st.warning("💡 근무표는 병원 양식에 따라 제목줄 위치가 다를 수 있습니다. 위 표에서 간호사 성함과 날짜(1일, 2일...)가 제대로 보이는지 확인해주세요.")

# --- 최종 확인 버튼 ---
st.markdown("---")
if file_p and file_a:
    if st.button("🚀 두 파일의 데이터 정합성 확인 완료! 다음 단계로"):
        st.balloons()
        st.info(f"{selected_year}년 {selected_month}의 계획과 실제 데이터를 매칭할 준비가 되었습니다. 이제 분석 로직을 가동할 수 있습니다.")
else:
    st.write("💡 분석을 시작하려면 두 개의 파일을 모두 업로드해주세요.")
