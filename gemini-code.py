# ... (기존 2단계 정제 완료 메시지 아래에 이어서 작성)

# 세션 상태에 데이터 저장 (탭 간 데이터 공유를 위해 필요)
if 'df_actual_final' not in st.session_state:
    st.session_state['df_actual_final'] = pd.DataFrame()

# 버튼 클릭 시 세션 상태 업데이트
if st.button("🚀 데이터 정제 및 매칭 실행"):
    df_plan_final = expand_plan_data(df_p_raw)
    df_actual_final = clean_actual_data(file_a, selected_year, selected_month_int)
    st.session_state['df_actual_final'] = df_actual_final
    # ... (기존 출력 로직)

# --- 3단계 탭 추가 ---
tab3 = st.tabs(["📊 3단계: 병동별 지원 현황 분석"])[0] # 기존 탭 뒤에 추가하거나 새로 정의

with tab3:
    df_actual = st.session_state.get('df_actual_final', pd.DataFrame())
    
    if not df_actual.empty:
        st.markdown(f"### 🏥 {selected_month_int}월 지원(P-코드) 상세 분석")
        
        # 상단 요약 지표 (Metrics)
        total_supports = len(df_actual)
        unique_nurses = df_actual['성함'].nunique()
        top_ward = df_actual['병동'].value_counts().idxmax()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("총 지원 건수", f"{total_supports}건")
        m2.metric("지원 투입 인원", f"{unique_nurses}명")
        m3.metric("최다 지원 병동", f"{top_ward}병동")
        
        st.divider()
        
        col_chart1, col_chart2 = st.columns([1, 1])
        
        with col_chart1:
            st.subheader("📍 병동별 지원받은 횟수")
            ward_counts = df_actual['병동'].value_counts().reset_index()
            ward_counts.columns = ['병동', '지원횟수']
            st.bar_chart(ward_counts.set_index('병동'))
            
        with col_chart2:
            st.subheader("👤 간호사별 지원 출동 횟수 (Top 10)")
            nurse_counts = df_actual['성함'].value_counts().head(10).reset_index()
            nurse_counts.columns = ['성함', '지원횟수']
            st.bar_chart(nurse_counts.set_index('성함'))

        st.divider()
        
        # 상세 데이터 필터링 및 테이블
        st.subheader("🔍 상세 지원 이력 조회")
        
        search_col1, search_col2 = st.columns(2)
        with search_col1:
            selected_ward = st.multiselect("분석할 병동 선택", options=sorted(df_actual['병동'].unique()))
        with search_col2:
            selected_nurse = st.multiselect("특정 간호사 조회", options=sorted(df_actual['성함'].unique()))
            
        # 필터링 로직
        filtered_df = df_actual.copy()
        if selected_ward:
            filtered_df = filtered_df[filtered_df['병동'].isin(selected_ward)]
        if selected_nurse:
            filtered_df = filtered_df[filtered_df['성함'].isin(selected_nurse)]
            
        # 결과 출력 (피벗 테이블 형태)
        st.write(f"검색 결과: {len(filtered_df)}건")
        
        # 날짜별/병동별로 누가 갔는지 한눈에 보기 위한 피벗
        if not filtered_df.empty:
            pivot_df = filtered_df.pivot_table(
                index=['날짜', '병동'], 
                values='성함', 
                aggfunc=lambda x: ", ".join(list(x))
            ).sort_values(by='날짜', ascending=False)
            
            st.dataframe(pivot_df, use_container_width=True)
            
            # CSV 다운로드 기능
            csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 지원 현황 결과 다운로드 (CSV)",
                data=csv,
                file_name=f"support_analysis_{selected_month_int}월.csv",
                mime="text/csv",
            )
        else:
            st.info("조건에 맞는 데이터가 없습니다.")
            
    else:
        st.warning("2단계에서 '데이터 정제 및 매칭 실행' 버튼을 클릭해야 분석이 가능합니다.")
