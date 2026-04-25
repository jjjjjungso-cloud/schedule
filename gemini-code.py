import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
import plotly.express as px

# --- [로직 1] 주간 계획 -> 평일 일별 데이터 확장 엔진 ---
def process_weekly_to_daily(df):
    # 1. 제목 공백 제거 및 표준화
    df.columns = [str(col).strip() for col in df.columns]
    
    # 2. 필수 컬럼 확인 (소영님의 새 양식 기준)
    required = ['시작일', '종료일', '근무조', '배정병동', '간호사 성함']
    if '성함' in df.columns and '간호사 성함' not in df.columns:
        df = df.rename(columns={'성함': '간호사 성함'})

    missing = [c for c in required if c not in df.columns]
    if missing:
        return None, f"⚠️ 필수 제목 중 {missing}을 찾을 수 없습니다. 엑셀 첫 줄의 제목을 확인해주세요!"

    expanded_results = []
    for _, row in df.iterrows():
        try:
            # 데이터 정제 (공백 제거 및 숫자 추출)
            name = str(row['간호사 성함']).strip()
            shift = str(row['근무조']).strip().upper()
            ward = re.sub(r'[^0-9]', '', str(row['배정병동'])) # '72병동' -> '72'
            
            s_date = pd.to_datetime(row['시작일'])
            e_date = pd.to_datetime(row['종료일'])

            # 기간 내 평일(월~금)만 자동 확장 루프
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

# --- [로직 2] 대시보드 UI 구성 ---
st.set_page_config(page_title="프라임 매니저 최종본", layout="wide")

st.title("🏥 프라임 팀 스마트 배정 분석 대시보드")
st.markdown("---")

# 사이드바 설정
st.sidebar.header("📁 데이터 업로드")
up_file = st.sidebar.file_uploader("작성하신 배정표(Excel)를 올려주세요", type=["xlsx"])

if up_file:
    xl = pd.ExcelFile(up_file)
    selected_sheet = st.sidebar.selectbox("분석할 시트(월)를 선택하세요", xl.sheet_names)
    
    if selected_sheet:
        df_raw = pd.read_excel(up_file, sheet_name=selected_sheet)
        
        # -------------------------------------------
        # 🔍 1단계: 컴퓨터가 인식한 파일 내용 확인 (소영님이 좋아하신 기능!)
        # -------------------------------------------
        st.subheader("🔍 1단계: 컴퓨터가 인식한 파일 내용")
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.info("💡 **인식된 열 제목 리스트**")
            # 실제 엑셀의 제목 상태를 보여줌
            st.write(list(df_raw.columns))
            
        with c2:
            st.info("💡 **데이터 미리보기 (상단 5줄)**")
            st.dataframe(df_raw.head(), use_container_width=True)

        st.markdown("---")

        # -------------------------------------------
        # 📊 2단계: 최종 분석 리포트 생성
        # -------------------------------------------
        if st.button("🚀 위 데이터가 맞습니다. 분석 시작!"):
            with st.spinner('평일 실적을 계산 중입니다...'):
                df_final, error = process_weekly_to_daily(df_raw)
                
                if error:
                    st.error(error)
                elif not df_final.empty:
                    st.success(f"✅ 분석 완료! 총 {len(df_final)}일치의 평일 지원 실적을 집계했습니다.")
                    
                    # 지표 요약
                    m1, m2, m3 = st.columns(3)
                    m1.metric("총 투입 인원", f"{df_final['성함'].nunique()}명")
                    m2.metric("총 지원 일수", f"{len(df_final)}일")
                    m3.metric("최다 지원 병동", f"{df_final['배정병동'].mode()[0]}번")

                    st.markdown("---")

                    # 결과 테이블과 차트
                    res_col, chart_col = st.columns([1.2, 1])
                    
                    with res_col:
                        st.markdown("#### 📋 상세 배정 리스트 (평일 확장본)")
                        st.dataframe(df_final.sort_values(by=['날짜', '성함']), height=500, use_container_width=True)
                        
                        # 다운로드 버튼 (CSV)
                        csv = df_final.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("📥 분석 결과 다운로드 (CSV)", csv, f"prime_analysis_{selected_sheet}.csv", "text/csv")

                    with chart_col:
                        st.markdown("#### 📈 간호사별 지원 일수")
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
                    st.warning("분석할 수 있는 데이터가 없습니다. 엑셀의 내용을 확인해주세요.")

else:
    # 초기 안내 메시지
    st.info("왼쪽 사이드바에서 엑셀 파일을 업로드하면 분석이 시작됩니다.")
    st.image("https://img.icons8.com/clouds/200/000000/google-sheets.png", width=100)
    st.write("※ 주의: 엑셀의 첫 번째 줄은 반드시 **시작일, 종료일, 근무조, 배정병동, 간호사 성함**이어야 합니다.")
