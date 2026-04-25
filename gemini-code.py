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
