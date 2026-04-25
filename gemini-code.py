import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta

# --- [수정] 실제 근무표 정제: 시트 이름에서 '월'만 정확히 추출 ---
def clean_actual_master(uploaded_file, year):
    xl = pd.ExcelFile(uploaded_file)
    actual_list = []
    
    for sheet_name in xl.sheet_names:
        # 시트 이름에서 1~12 사이의 숫자만 월로 인식 (2026 같은 연도 제외)
        nums = re.findall(r'\d+', sheet_name)
        month_int = None
        for n in nums:
            if 1 <= int(n) <= 12:
                month_int = int(n)
                break
        
        if month_int is None:
            continue # 월을 찾을 수 없는 시트(예: 'Sheet1')는 건너뜀
        
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        
        # 이름/날짜 열 자동 찾기 로직 강화
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, c in enumerate(df.columns) if '일' in str(c)]
        
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            if name in ['nan', '명', '', 'None']: continue
            
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward_match = re.search(r'/(\d+)', code)
                    if ward_match:
                        shift = 'D' if ('D4' in code or 'D' in code) else 'E'
                        try:
                            actual_list.append({
                                '날짜': datetime(year, month_int, int(d_match[0])),
                                '성함': name,
                                '실제근무조': shift,
                                '실제병동': str(int(ward_match.group(1)))
                            })
                        except: continue
    return pd.DataFrame(actual_list)

# --- [수정] 배정표 정제: 제목이 없을 경우를 대비한 유연한 처리 ---
def expand_plan_master(uploaded_file):
    xl = pd.ExcelFile(uploaded_file)
    combined_list = []
    # 찾고자 하는 핵심 키워드
    keywords = {'시작일': '시작일', '종료일': '종료일', '근무조': '근무조', '배정병동': '병동', '간호사 성함': '성함'}
    
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        
        # 실제 엑셀의 컬럼명과 매칭 시도
        col_map = {}
        for key, val in keywords.items():
            found_col = next((c for c in df.columns if val in str(c)), None)
            if found_col: col_map[key] = found_col

        if len(col_map) < 5: continue # 필수 항목이 부족하면 건너뜀
            
        for _, row in df.iterrows():
            try:
                start_dt = pd.to_datetime(row[col_map['시작일']])
                end_dt = pd.to_datetime(row[col_map['종료일']])
                curr = start_dt
                while curr <= end_dt:
                    combined_list.append({
                        '날짜': curr,
                        '성함': str(row[col_map['간호사 성함']]).strip(),
                        '계획근무조': row[col_map['근무조']],
                        '계획병동': str(row[col_map['배정병동']])
                    })
                    curr += timedelta(days=1)
            except: continue
    return pd.DataFrame(combined_list).drop_duplicates()

# --- (이후 메인 로직 및 pd.merge 부분은 동일) ---
