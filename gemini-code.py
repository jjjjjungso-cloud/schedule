import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [기본 설정 및 유틸리티 함수는 이전과 동일] ---
WARD_GROUPS = {
    '1동': ['41', '51', '52', '61', '62', '71', '72', '91', '92', '101', '102', '111', '122', '131'],
    '2동': ['66', '75', '76', '85', '86', '96', '105', '106', '116']
}
NURSE_GROUPS = {
    '1동': ['정윤정', '기아현', '김유진', '정하라', '김한솔', '최휘영', '박소영'],
    '2동': ['박가영', '홍현의', '김민정', '정소영', '문선희', '엄현지']
}
NURSE_TO_BLD = {name: bld for bld, names in NURSE_GROUPS.items() for name in names}
WARD_TO_BLD = {ward: bld for bld, wards in WARD_GROUPS.items() for ward in wards}

def expand_generic_data(df):
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동']
    if not all(col in df.columns for col in required): return pd.DataFrame()
    for _, row in df.iterrows():
        try:
            start_dt = pd.to_datetime(row['시작일'])
            end_dt = pd.to_datetime(row['종료일'])
            curr = start_dt
            while curr <= end_dt:
                if curr.weekday() < 5:
                    expanded_list.append({
                        '날짜': curr,
                        '주차': f"{curr.isocalendar().week}주차",
                        '성함': str(row.get('간호사 성함', '')).strip(),
                        '계획근무조': str(row['근무조']).strip(),
                        '계획병동': str(row['배정병동']),
                        '시작일': start_dt.strftime('%Y-%m-%d'),
                        '종료일': end_dt.strftime('%Y-%m-%d')
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)

# --- [4단계 로직 업데이트] ---
with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_master = st.session_state.df_master
        df_req = st.session_state.df_req_next
        st.header("🎯 데이터 기반 5월 배정 의사결정")

        # 1. 주차 선택 및 일자 범위 표시
        weeks = sorted(df_req['주차'].unique())
        selected_week = st.selectbox("배정 주차 선택", weeks)
        
        # 해당 주차의 실제 날짜 범위 추출
        week_info = df_req[df_req['주차'] == selected_week]
        date_range = f"{week_info['시작일'].min()} ~ {week_info['종료일'].max()}"
        st.subheader(f"📅 {selected_week} ({date_range})")

        # 2. 간호사 선택
        nurse_list = sorted(list(NURSE_TO_BLD.keys()))
        selected_nurse = st.selectbox("간호사를 선택하세요", nurse_list)
        
        # 3. 근무조 패턴 분석 및 선택
        st.divider()
        col_logic, col_select = st.columns(2)
        
        with col_logic:
            st.subheader("⚙️ 근무조 패턴 분석")
            # 직전 이력 추출 (2주 블록 로직)
            target_dt_str = week_info['시작일'].min()
            hist_list = get_recent_history_list(df_master, selected_nurse, target_dt_str)
            rec_shift = recommend_shift_logic(hist_list)
            st.write(f"📌 **{selected_nurse}** 직전 이력: `{ ' -> '.join(hist_list) if hist_list else '데이터 없음' }`")
            st.info(f"💡 **패턴 분석 결과:** 차주 추천 근무는 **{rec_shift}**입니다.")

        with col_select:
            st.subheader("⌨️ 근무조 최종 선택")
            final_shift = st.radio("배정할 근무조를 선택하세요", ["D", "E"], 
                                   index=0 if rec_shift == "D" else 1, horizontal=True)

        # 4. 병동 추천 로직 (최소 누적 방문 기준)
        st.divider()
        st.subheader(f"🏥 {selected_nurse} 간호사 최적 병동 추천")
        allow_switch = st.checkbox("🚩 타 동(Building) 스위치 허용")
        
        # 해당 주차 & 선택 근무조 지원 요청 병동 필터링
        avail_today = df_req[(df_req['주차'] == selected_week) & (df_req['계획근무조'] == final_shift)]
        
        if not avail_today.empty:
            my_bld = NURSE_TO_BLD.get(selected_nurse, "1동")
            # 2026년 전체 누적 데이터 기반 카운트
            ward_counts = df_master[df_master['성함'] == selected_nurse].groupby('계획병동').size().to_dict()
            
            recommend_list = []
            for w in avail_today['계획병동'].unique():
                if not allow_switch and WARD_TO_BLD.get(w) != my_bld: continue
                count = ward_counts.get(w, 0)
                recommend_list.append({
                    "병동": w, "소속": WARD_TO_BLD.get(w, "기타"),
                    "누적 방문일수": count
                })
            
            if recommend_list:
                res_df = pd.DataFrame(recommend_list).sort_values(by="누적 방문일수")
                st.write(f"**[{final_shift} 근무조 후보 병동 및 누적 기록]**")
                st.dataframe(res_df, use_container_width=True)
                
                # 최종 추천 (누적 방문일수가 가장 적은 것)
                top = res_df.iloc[0]
                st.success(f"🏆 최종 추천: **{top['병동']}병동** (근거: 누적 방문 {top['누적 방문일수']}회로 가장 적음)")
            else:
                st.warning(f"{my_bld} 내에 해당 근무조({final_shift}) 요청 병동이 없습니다. 스위치를 허용해 보세요.")
        else:
            st.error(f"해당 주차에 {final_shift} 근무조 지원 요청이 없습니다.")
    else:
        st.info("1, 2단계 파일 업로드 및 분석을 먼저 완료해 주세요.")
