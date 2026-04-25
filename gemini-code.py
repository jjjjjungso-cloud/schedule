import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. 데이터 정제 및 평일 확장 엔진 ---
def process_prime_weekly_plan(df):
    # 열 이름의 공백 제거 및 정제
    df.columns = [str(col).strip() for col in df.columns]
    
    # 필수 열 정의 (소영님의 새로운 양식 기준)
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    
    # '성함' 보정 로직
    if '성함' in df.columns and '간호사 성함' not in df.columns:
        df = df.rename(columns={'성함': '간호사 성함'})

    missing = [c for c in required if c not in df.columns]
    if missing:
        return None, f"⚠️ 필수 제목 중 {missing}을 찾을 수 없습니다. 엑셀 상단의 제목을 확인해주세요!"

    expanded_results = []
    for _, row in df.iterrows():
        try:
            # 기본 정보 추출 및 세척
            name = str(row['간호사 성함']).strip()
            shift = str(row['근무조']).strip().upper()
            ward = re.sub(r'[^0-9]', '', str(row['배정병동'])) # '72병동' -> '72'
            
            s_date = pd.to_datetime(row['시작일'])
            e_date = pd.to_datetime(row['종료일'])

            # 기간 내 평일(월~금)만 자동 확장
            curr = s_date
            while curr <= e_date:
                if curr.weekday() < 5:  # 0:월 ~ 4:금 (주말 제외)
                    expanded_results.append({
                        '날짜': curr.strftime('%Y-%m-%d'),
                        '요일': ['월', '화', '수', '목', '금'][curr.weekday()],
                        '성함': name,
                        '배정병동': ward,
                        '근무조': shift
                    })
                curr += timedelta(days=1)
        except:
            continue
            
    return pd.DataFrame(expanded_results).drop_duplicates(), None

# --- 2. 대시보드 UI 구성 ---
st.set_page_config(page_title="프라임 매니저 대시보드", layout="wide")

st.title("🏥 프라임 팀 스마트 배정 분석 대시보드")
st.markdown("---")

# 파일 업로드
up_file = st.sidebar.file_uploader("작성하신 배정표(Excel)를 업로드하세요", type=["xlsx"])

if up_file:
    xl = pd.ExcelFile(up_file)
    selected_sheet = st.sidebar.selectbox("분석할 시트(월)를 선택하세요", xl.sheet_names)
    
    if selected_sheet:
        df_raw = pd.read_excel(up_file, sheet_name=selected_sheet)
        
        # [1단계: 데이터 투명성 확인창]
        st.subheader("🔍 1단계: 데이터 로드 확인")
        col_header, col_preview = st.columns([1, 2])
        
        with col_header:
            st.info("💡 **인식된 열 제목**")
            st.write(list(df_raw.columns))
            
        with col_preview:
            st.info("💡 **원본 데이터 미리보기**")
            st.dataframe(df_raw.head(), use_container_width=True)

        st.markdown("---")

        # [2단계: 분석 결과 대시보드]
        if st.button("🚀 데이터 확인 완료! 분석 및 리포트 생성"):
            df_final, error = process_prime_weekly_plan(df_raw)
            
            if error:
                st.error(error)
            elif not df_final.empty:
                st.success(f"✅ {selected_sheet} 시트 분석 완료! 총 {len(df_final)}일치의 평일 실적을 찾았습니다.")
                
                # 1. 상단 요약 지표 (Metrics)
                st.markdown("### 📊 운영 현황 요약")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("총 투입 인원", f"{df_final['성함'].nunique()}명")
                m2.metric("총 지원 일수", f"{len(df_final)}일")
                m3.metric("최다 지원 병동", f"{df_final['배정병동'].mode()[0]}병동")
                m4.metric("D4 근무 포함", "YES (D와 동일 인정)")

                st.markdown("---")

                # 2. 시각화 영역 (Charts)
                res_col, chart_col = st.columns([1.2, 1])
                
                with res_col:
                    st.markdown("#### 📋 상세 배정 리스트 (평일 확장본)")
                    st.dataframe(df_final.sort_values(by=['날짜', '성함']), height=500, use_container_width=True)
                    
                    # 다운로드 버튼
                    csv = df_final.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📥 분석 결과 다운로드 (CSV)", csv, f"prime_{selected_sheet}_report.csv", "text/csv")

                with chart_col:
                    st.markdown("#### 📈 간호사별 누적 지원 일수")
                    name_stats = df_final['성함'].value_counts().reset_index()
                    name_stats.columns = ['성함', '지원일수']
                    fig_name = px.bar(name_stats, x='성함', y='지원일수', color='지원일수', text_auto=True, color_continuous_scale='Teal')
                    st.plotly_chart(fig_name, use_container_width=True)

                    st.markdown("#### 🏥 병동별 배정 비중")
                    ward_stats = df_final['배정병동'].value_counts().reset_index()
                    ward_stats.columns = ['병동', '횟수']
                    fig_ward = px.pie(ward_stats, values='횟수', names='병동', hole=0.3)
                    st.plotly_chart(fig_ward, use_container_width=True)

            else:
                st.warning("분석할 수 있는 데이터가 없습니다. 양식의 내용을 확인해주세요.")

else:
    st.info("왼쪽 사이드바에서 엑셀 파일을 업로드하면 스마트 분석 대시보드가 활성화됩니다.")
