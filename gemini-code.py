import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. 데이터 처리 핵심 엔진 ---
def process_schedule_data(df):
    results = []
    # 컬럼명 유연하게 대응 (공백 제거)
    df.columns = [col.strip() for col in df.columns]
    
    # 필수 컬럼 존재 확인
    required_cols = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    if not all(col in df.columns for col in required_cols):
        return pd.DataFrame(), "필수 컬럼(시작일, 종료일, 근무조, 배정병동, 간호사 성함)이 누락되었습니다."

    for _, row in df.iterrows():
        try:
            # 데이터 정제
            name = str(row['간호사 성함']).strip()
            shift = str(row['근무조']).strip().upper()
            # 병동 번호에서 숫자만 추출 (예: '72병동' -> '72')
            ward = re.sub(r'[^0-9]', '', str(row['배정병동']))
            
            s_date = pd.to_datetime(row['시작일'])
            e_date = pd.to_datetime(row['종료일'])

            # 기간 내 평일(월~금) 추출 로직
            curr = s_date
            while curr <= e_date:
                if curr.weekday() < 5:  # 0:월 ~ 4:금
                    results.append({
                        '날짜': curr.strftime('%Y-%m-%d'),
                        '요일': ['월', '화', '수', '목', '금', '토', '일'][curr.weekday()],
                        '성함': name,
                        '배정병동': ward,
                        '근무조': shift
                    })
                curr += timedelta(days=1)
        except:
            continue
            
    return pd.DataFrame(results), None

# --- 2. 대시보드 UI 구성 ---
st.set_page_config(page_title="프라임 매니저 대시보드", layout="wide")

st.title("🏥 프라임 팀 스마트 배정 분석 시스템")
st.markdown("---")

# 파일 업로드
uploaded_file = st.sidebar.file_uploader("배정표(Excel) 파일을 업로드하세요", type=["xlsx"])

if uploaded_file:
    # 엑셀의 모든 시트 이름 가져오기
    xl = pd.ExcelFile(uploaded_file)
    sheet_names = xl.sheet_names
    
    selected_sheet = st.sidebar.selectbox("분석할 시트(월)를 선택하세요", sheet_names)
    
    if selected_sheet:
        df_raw = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
        df_final, error = process_schedule_data(df_raw)
        
        if error:
            st.error(error)
        elif df_final.empty:
            st.warning("분석할 수 있는 배정 데이터가 없습니다. 양식을 확인해주세요.")
        else:
            # 상단 요약 지표
            st.subheader(f"📊 {selected_sheet} 운영 현황 요약")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("총 투입 인원(중복 제외)", f"{df_final['성함'].nunique()}명")
            with c2:
                st.metric("총 지원 일수(평일 기준)", f"{len(df_final)}일")
            with c3:
                st.metric("가장 많이 지원한 병동", f"{df_final['배정병동'].mode()[0]}병동")

            st.markdown("---")

            # 좌측: 데이터 테이블 / 우측: 차트
            col_left, col_right = st.columns([1.2, 1])
            
            with col_left:
                st.markdown("#### 📋 상세 배정 리스트")
                st.dataframe(df_final.sort_values(by=['날짜', '성함']), use_container_width=True, height=500)
                
                # CSV 다운로드 버튼
                csv = df_final.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 분석 결과 다운로드 (CSV)", csv, f"prime_analysis_{selected_sheet}.csv", "text/csv")

            with col_right:
                st.markdown("#### 📈 간호사별 지원 실적 (일수)")
                count_df = df_final['성함'].value_counts().reset_index()
                count_df.columns = ['성함', '지원일수']
                fig_name = px.bar(count_df, x='성함', y='지원일수', color='지원일수', 
                                 color_continuous_scale='Viridis', text_auto=True)
                st.plotly_chart(fig_name, use_container_width=True)

                st.markdown("#### 🏥 병동별 지원 분포")
                ward_df = df_final['배정병동'].value_counts().reset_index()
                ward_df.columns = ['병동', '지원횟수']
                fig_ward = px.pie(ward_df, values='지원횟수', names='병동', hole=0.4)
                st.plotly_chart(fig_ward, use_container_width=True)

            # 근무조별 분포
            st.markdown("---")
            st.markdown("#### ⏰ 근무조별 배정 현황")
            shift_df = df_final.groupby(['근무조', '요일']).size().unstack(fill_value=0)
            st.table(shift_df)

else:
    # 파일이 업로드되지 않았을 때의 안내 화면
    st.info("왼쪽 사이드바에서 배정표 파일을 업로드하면 분석이 시작됩니다.")
    
    # 샘플 구조 안내
    with st.expander("📌 올바른 엑셀 양식 확인하기"):
        sample_df = pd.DataFrame({
            "시작일": ["2026-03-02", "2026-03-02"],
            "종료일": ["2026-03-06", "2026-03-06"],
            "근무조": ["D", "E"],
            "배정병동": ["72", "116"],
            "간호사 성함": ["박소영", "정윤정"]
        })
        st.table(sample_df)
        st.write("※ 위와 같은 컬럼명이 반드시 포함되어야 합니다.")
