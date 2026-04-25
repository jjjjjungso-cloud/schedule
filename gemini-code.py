import streamlit as st
import pandas as pd

st.title("🏥 1단계: 배정표(Plan) 데이터 확인")

# 1. 파일 업로드
file_p = st.file_uploader("배정표(.xlsx) 파일을 업로드하세요", type="xlsx")

if file_p:
    # 엑셀 읽기
    xl = pd.ExcelFile(file_p)
    selected_sheet = st.selectbox("분석할 시트를 선택하세요", xl.sheet_names)
    df_raw = pd.read_excel(file_p, sheet_name=selected_sheet)

    st.markdown("---")
    st.subheader("🔍 원본 데이터 확인 (상위 5행)")
    st.dataframe(df_raw.head())

    # 2. 열 정제 (C, D, F, G, J, K, M, N, P, Q 삭제 후 필요한 열만 선택)
    # E(성함/정보), H, I, L, O 열 위주로 추출 (인덱스로 접근하는 것이 안전함)
    # 엑셀의 E열은 인덱스 4, H는 7, I는 8, L은 11, O는 14입니다.
    
    try:
        # 사용자 요청에 따른 특정 열 추출
        # E(4), H(7), I(8), L(11), O(14) 열 선택
        df_selected = df_raw.iloc[:, [4, 7, 8, 11, 14]].copy()
        
        # 열 이름 정리 (예시: 성함, 대기병동, 지원1, 지원2, 지원3 등)
        # 실제 데이터 내용에 따라 이름을 붙여줍니다.
        df_selected.columns = ['성함_정보', '데이터1', '데이터2', '데이터3', '데이터4']
        
        st.success("✅ 요청하신 열(E, H, I, L, O) 추출에 성공했습니다.")
        
        # 3. 데이터 확인 및 필터링
        # 성함 정보가 비어있지 않은 데이터만 보기
        df_clean = df_selected.dropna(subset=['성함_정보']).reset_index(drop=True)
        
        st.subheader("📋 정제된 배정표 리스트")
        st.dataframe(df_clean, use_container_width=True)
        
        st.info("💡 위 표에서 '성함'과 '병동 정보'가 제대로 분리되어 보이나요? 확인 후 2단계(근무표)로 넘어가겠습니다.")

    except Exception as e:
        st.error(f"열 추출 중 오류가 발생했습니다: {e}")
        st.warning("엑셀의 열 개수가 부족하거나 형식이 다를 수 있습니다. 업로드한 파일의 구조를 다시 확인해주세요.")
