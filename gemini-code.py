import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [설정 데이터] 팀장님이 관리하는 구역 ---
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

# 등록된 진짜 병동 번호 리스트 (에러 및 가짜 병동 차단용)
VALID_WARDS = [str(w) for wards in WARD_GROUPS.values() for w in wards]

# --- [유틸리티 함수] ---

def expand_generic_data(df):
    """배정표(Plan) 정제"""
    expanded_list = []
    required = ['시작일', '종료일', '근무조', '배정병동']
    if not all(any(req in c for c in df.columns) for req in required):
        return pd.DataFrame()
    
    c_start = next(c for c in df.columns if '시작일' in c)
    c_end = next(c for c in df.columns if '종료일' in c)
    c_shift = next(c for c in df.columns if '근무조' in c)
    c_ward = next(c for c in df.columns if '병동' in c)
    c_name = next((c for c in df.columns if '성함' in c), None)

    for _, row in df.iterrows():
        try:
            start_dt = pd.to_datetime(row[c_start])
            end_dt = pd.to_datetime(row[c_end])
            curr = start_dt
            while curr <= end_dt:
                if curr.weekday() < 5: 
                    expanded_list.append({
                        '날짜': curr,
                        '주차': f"{curr.isocalendar().week}주차",
                        '성함': str(row[c_name]).strip() if c_name and pd.notna(row[c_name]) else "",
                        '계획근무조': str(row[c_shift]).strip().upper(),
                        '계획병동': str(row[c_ward]).strip(),
                    })
                curr += timedelta(days=1)
        except: continue
    return pd.DataFrame(expanded_list)


def clean_actual_data(uploaded_file, year, month_int):
    """[핵심] 실제 근무표 정제: 슬래시(/)와 숫자 사냥 공식 완벽 적용"""
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        name_cols = [i for i, c in enumerate(df.columns) if '명' in str(c) or '성함' in str(c)]
        if not name_cols: continue
        name_idx = name_cols[0]
        
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '', 'None']: continue
            
            for d_idx in day_cols:
                col_name = str(df.columns[d_idx])
                d_match = re.findall(r'\d+', col_name)
                if not d_match: continue
                
                code = str(row.iloc[d_idx]).strip().upper()
                
                # 오프(/), 빈칸, 병가 등은 즉각 무시
                if code in ['NAN', 'NONE', '', '/'] or '병' in code or '건' in code or '휴' in code:
                    continue
                
                # --- 스케줄표 해독 시작 ---
                actual_ward = ""
                shift = ""
                
                # 케이스 1: 팀장님 공식대로 슬래시(/)가 있는 경우 (파견)
                if '/' in code:
                    parts = code.split('/', 1)
                    front, back = parts[0], parts[1]
                    
                    # 뒤(back)에서 병동 숫자 추출
                    ward_nums = re.findall(r'\d+', back)
                    if ward_nums and ward_nums[0] in VALID_WARDS:
                        actual_ward = ward_nums[0]
                    
                    # 앞(front)에서 근무조 추출
                    if 'E' in front: shift = 'E'
                    elif 'N' in front: shift = 'N'
                    else: shift = 'D'
                    
                # 케이스 2: 슬래시가 없는 경우 (단순 숫자, 혹은 정상 근무 기호)
                else:
                    # 셀 안에서 '진짜 병동 번호'가 있는지 사냥 (예: 66, D66)
                    nums = re.findall(r'\d+', code)
                    for num in nums:
                        if num in VALID_WARDS:
                            actual_ward = num
                            break
                    
                    # 근무조 판별
                    if 'E' in code: shift = 'E'
                    elif 'N' in code: shift = 'N'
                    else: shift = 'D' # D4, 66 등은 모두 D로 기본 처리

                # 💡 만약 병동 번호를 못 찾았다면? -> '자기 소속 동'에서 정상 근무한 것으로 간주!
                # (그래야 계획과 비교해서 '불일치'가 아님을 증명할 수 있음)
                if not actual_ward:
                    # 이름으로 기본 소속동 찾기 (1동/2동)
                    my_bld = NURSE_TO_BLD.get(name, "1동")
                    # 정상 근무자 처리를 위해 '정상근무'라는 마커만 남겨둡니다. 
                    # 어차피 5단계 비교 시 '계획'과 숫자가 다르면 파견으로 처리되므로, 빈칸만 아니면 됨
                    actual_ward = "정상근무"

                try:
                    actual_list.append({
                        '날짜': datetime(year, month_int, int(d_match[0])),
                        '성함': name,
                        '실제근무조': shift,
                        '실제병동': actual_ward
                    })
                except: continue
                    
    return pd.DataFrame(actual_list)

def recommend_shift_logic(history_list):
    if not history_list: return "D"
    last_shift = history_list[-1]
    count = 0
    for s in reversed(history_list):
        if s == last_shift: count += 1
        else: break
    return last_shift if count < 2 else ("D" if last_shift == "E" else "E")

def get_recent_history_list(df, nurse_name, target_date):
    if df.empty: return []
    target_dt = pd.to_datetime(target_date)
    start_dt = target_dt - timedelta(weeks=5)
    hist = df[(df['성함'] == nurse_name) & (df['날짜'] >= start_dt) & (df['날짜'] < target_dt)]
    if hist.empty: return []
    return hist.sort_values('날짜').groupby('주차')['계획근무조'].first().tolist()


# --- 메인 UI ---
st.set_page_config(page_title="프라임 배정 최적화 시스템", layout="wide")
st.title("🏥 프라임 데이터 통합 및 배정 최적화 시스템")

if 'df_master' not in st.session_state: st.session_state.df_master = pd.DataFrame()
if 'df_req_next' not in st.session_state: st.session_state.df_req_next = pd.DataFrame()

st.sidebar.header("📅 기준 설정")
selected_year = st.sidebar.selectbox("연도", [2026, 2027], index=0)
selected_month = st.sidebar.selectbox("과거 실제근무 기준 월", [f"{i}월" for i in range(1, 13)], index=3) # 4월 세팅
month_int = int(re.findall(r'\d+', selected_month)[0])

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📂 1단계: 업로드", "🔍 2단계: 정제", "📊 3단계: 분석", "🎯 4단계: 배정", "📋 5단계: 결원대체 확인"])

with tab1:
    st.info("💡 배정을 위해 3가지 파일을 모두 업로드하세요.")
    c1, c2, c3 = st.columns(3)
    file_p = c1.file_uploader("과거 배정표(Plan)", type=["xlsx", "csv"])
    file_a = c2.file_uploader("과거 실제 근무표(Actual)", type=["xlsx", "csv"])
    file_r = c3.file_uploader("차월 지원 요청 파일(Request)", type=["xlsx", "csv"])

with tab2:
    if file_p and file_a and file_r:
        if st.button("🚀 데이터 통합 정제 시작"):
            st.session_state.df_master = pd.DataFrame() # 메모리 찌꺼기 완벽 청소
            try:
                def load_df(f): return pd.read_csv(f) if f.name.endswith('csv') else pd.read_excel(f)
                
                df_p = expand_generic_data(load_df(file_p))
                df_a = clean_actual_data(file_a, selected_year, month_int)
                
                if df_p.empty or df_a.empty:
                    st.error("🚨 데이터 파싱 실패: 파일 양식이나 컬럼명을 확인해 주세요.")
                else:
                    df_p['날짜'] = pd.to_datetime(df_p['날짜'])
                    df_a['날짜'] = pd.to_datetime(df_a['날짜'])
                    df_p['성함'] = df_p['성함'].astype(str).str.strip()
                    df_a['성함'] = df_a['성함'].astype(str).str.strip()
                
                    df_master_new = pd.merge(df_p, df_a, on=['날짜', '성함'], how='left')
                    st.session_state.df_master = df_master_new
                    st.session_state.df_req_next = expand_generic_data(load_df(file_r))
                    st.success("✅ 정제 및 마스터 결합 완료! 5단계 탭에서 결과를 확인하세요.")
            except Exception as e:
                st.error(f"🚨 시스템 오류가 발생했습니다: {e}")
    else: st.warning("파일을 모두 업로드해 주세요.")

with tab3:
    if not st.session_state.df_master.empty and '계획병동' in st.session_state.df_master.columns:
        st.subheader("🕵️‍♀️ 간호사별 병동 지원 일수 (경험 매트릭스)")
        exp_matrix = st.session_state.df_master.groupby(['성함', '계획병동']).size().unstack(fill_value=0)
        st.dataframe(exp_matrix, use_container_width=True)
    elif not st.session_state.df_master.empty:
        st.error("🚨 2단계에서 정제를 다시 눌러주세요.")
    else: st.info("2단계를 먼저 실행하세요.")

with tab4:
    if not st.session_state.df_master.empty and not st.session_state.df_req_next.empty:
        df_master = st.session_state.df_master
        df_req = st.session_state.df_req_next
        st.header("🎯 차월 배정 의사결정")
        weeks = sorted(df_req['주차'].unique())
        selected_week = st.selectbox("배정 주차 선택", weeks)
        week_info = df_req[df_req['주차'] == selected_week]
        
        date_range_start = week_info['날짜'].min()
        date_range_end = week_info['날짜'].max()
        date_range = f"{date_range_start.strftime('%Y-%m-%d')} ~ {date_range_end.strftime('%Y-%m-%d')}" if hasattr(date_range_start, 'strftime') else f"{date_range_start} ~ {date_range_end}"
        st.subheader(f"📅 {selected_week} ({date_range})")

        all_nurses = sorted(list(NURSE_TO_BLD.keys()))
        selected_nurse = st.selectbox("간호사를 선택하세요", all_nurses)
        
        st.divider()
        col_logic, col_select = st.columns(2)
        with col_logic:
            st.subheader("⚙️ 근무조 패턴 분석")
            hist_list = get_recent_history_list(df_master, selected_nurse, week_info['날짜'].min())
            rec_shift = recommend_shift_logic(hist_list)
            st.write(f"📌 **{selected_nurse}** 직전 이력: `{ ' -> '.join(hist_list) if hist_list else '데이터 없음' }`")
            st.info(f"💡 **패턴 분석 결과:** 차주 추천 근무는 **{rec_shift}**입니다.")
        
        with col_select:
            st.subheader("⌨️ 근무조 최종 선택")
            final_shift = st.radio("배정할 근무조 선택", ["D", "E"], index=0 if rec_shift == "D" else 1, horizontal=True)

        st.divider()
        st.subheader(f"🏥 {selected_nurse} 간호사 최적 병동 추천")
        allow_switch = st.checkbox("🚩 타 동(Building) 스위치 허용")
        
        avail_today = df_req[(df_req['주차'] == selected_week) & (df_req['계획근무조'] == final_shift)]
        if not avail_today.empty:
            my_bld = NURSE_TO_BLD.get(selected_nurse, "1동")
            ward_counts = df_master[df_master['성함'] == selected_nurse].groupby('계획병동').size().to_dict()
            recommend_list = []
            for w in avail_today['계획병동'].unique():
                if not allow_switch and WARD_TO_BLD.get(w) != my_bld: continue
                count = ward_counts.get(w, 0)
                recommend_list.append({"병동": w, "소속": WARD_TO_BLD.get(w, "기타"), "누적 방문일수": count})
            if recommend_list:
                res_df = pd.DataFrame(recommend_list).sort_values(by="누적 방문일수")
                st.dataframe(res_df, use_container_width=True)
                top = res_df.iloc[0]
                st.success(f"🏆 최종 추천: **{top['병동']}병동** (누적 방문 {top['누적 방문일수']}회로 가장 적음)")
            else: st.warning(f"{my_bld} 내 지원 요청이 없습니다.")
        else: st.error(f"해당 주차에 {final_shift} 근무조 요청이 없습니다.")
    else: st.info("1, 2단계를 먼저 완료해 주세요.")


# --- 📋 5단계: 결원대체 이력 확인 (퍼펙트 로직 탑재) ---
with tab5:
    if not st.session_state.df_master.empty and '계획병동' in st.session_state.df_master.columns:
        st.header(f"📋 {selected_month} 결원대체(비상 투입) 이력 확인")
        
        df_m = st.session_state.df_master.copy()
        
        if '실제병동' not in df_m.columns:
            st.error("🚨 2단계에서 실제 근무표의 병동 데이터가 합쳐지지 않았습니다. 파일 형식을 다시 확인해 주세요.")
        else:
            # 1. 비교를 위해 병동 텍스트에서 숫자만 엄밀하게 추출
            df_m['계획_비교'] = df_m['계획병동'].astype(str).str.extract(r'(\d+)')[0].fillna('')
            df_m['실제_비교'] = df_m['실제병동'].astype(str).str.extract(r'(\d+)')[0].fillna('')
            
            # 2. [가장 완벽한 결원대체 필터 공식]
            # - 실제 기록이 존재하고 (결측치 제외)
            # - 실제 기록이 '정상근무'가 아니며 (D, E4 등 자기 병동 근무자 제외)
            # - 계획된 병동 숫자와 파견된 병동 숫자가 다른 경우!
            df_sub = df_m[
                (df_m['실제_비교'] != '') & 
                (df_m['실제병동'] != '정상근무') &
                (df_m['계획_비교'] != df_m['실제_비교'])
            ].copy()
            
            if not df_sub.empty:
                st.subheader("📊 간호사별 비상 투입 횟수 (피로도 모니터링)")
                pivot_df = df_sub.groupby(['성함', '실제_비교']).size().unstack(fill_value=0)
                pivot_df.columns = [f"{col}병동" for col in pivot_df.columns]
                pivot_df['총 출동횟수'] = pivot_df.sum(axis=1)
                
                pivot_df = pivot_df.sort_values('총 출동횟수', ascending=False)
                st.dataframe(pivot_df.style.background_gradient(cmap='Reds', subset=['총 출동횟수']), use_container_width=True)
                
                st.divider()
                
                st.subheader(f"📅 일자별 상세 결원대체 리스트")
                res_df = df_sub[['날짜', '성함', '계획병동', '실제병동', '실제근무조']].copy()
                res_df['계획병동'] = res_df['계획병동'].apply(lambda x: str(x) if '병동' in str(x) else f"{x}병동")
                res_df['실제병동'] = res_df['실제병동'].apply(lambda x: str(x) if '병동' in str(x) else f"{x}병동")
                res_df = res_df.rename(columns={'계획병동': '원래계획', '실제병동': '실제 근무', '실제근무조': '근무조'})
                res_df['날짜'] = pd.to_datetime(res_df['날짜']).dt.strftime('%Y-%m-%d')
                
                search_nurse = st.multiselect("특정 간호사 이력 필터링", options=sorted(res_df['성함'].unique()))
                if search_nurse:
                    res_df = res_df[res_df['성함'].isin(search_nurse)]
                
                st.dataframe(res_df.sort_values('날짜', ascending=False), use_container_width=True, hide_index=True)
                
            else:
                st.success("🎉 분석 결과: 계획표와 실제 근무표가 일치합니다! 결원대체 파견 건이 없습니다.")
    else:
        st.warning("📂 1, 2단계를 통해 데이터를 먼저 통합 정제해 주세요.")
