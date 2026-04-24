import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime, timedelta

# --- 1. 데이터베이스 초기화 및 초기 데이터 세팅 ---
def init_db():
    conn = sqlite3.connect('prime_nurse.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS nurses (
                    name TEXT PRIMARY KEY, unit TEXT, sub_count INTEGER DEFAULT 0,
                    last_d_dedicated TEXT, visited_wards TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS assignment_logs (
                    date TEXT, name TEXT, plan_ward TEXT, actual_ward TEXT,
                    shift TEXT, status TEXT, UNIQUE(date, name))''')
    conn.commit()
    conn.close()

def register_initial_nurses():
    """서무 업무자를 제외한 실제 병동 근무 프라임 간호사 13명 등록"""
    nurses = [
        ('정윤정', '1동'), ('최휘영', '1동'), ('기아현', '1동'), ('김유진', '1동'),
        ('정하라', '1동'), ('박소영', '1동'), ('박가영', '1동'),
        ('정소영', '2동'), ('홍현의', '2동'), ('문선희', '2동'), ('김민정', '2동'),
        ('김한솔', '2동'), ('이선아', '2동')
    ]
    conn = sqlite3.connect('prime_nurse.db')
    c = conn.cursor()
    for name, unit in nurses:
        c.execute("INSERT OR IGNORE INTO nurses (name, unit) VALUES (?, ?)", (name, unit))
    conn.commit()
    conn.close()

# --- 2. 데이터 분석 엔진 (고정민 님 제외 필터 추가) ---
def analyze_data(up_p, up_a, year, month_val):
    # 1. 계획표 분석
    p_sheets = pd.read_excel(up_p, sheet_name=None)
    plan_list = []
    for _, df in p_sheets.items():
        date_cols = [i for i, c in enumerate(df.columns) if '~' in str(c)]
        shift_idx = next((i for i, c in enumerate(df.columns) if '근무조' in str(c)), 1)
        for _, row in df.iterrows():
            shift_val = str(row.iloc[shift_idx])
            shift = 'D' if 'D' in shift_val else 'E'
            for c_idx in date_cols:
                # [수정] 성함 추출 시 고정민 님 제외
                match = re.search(r'(\d+)\s*[\n\r\s]+\s*([가-힣]+)', str(row.iloc[c_idx]))
                if match:
                    name = match.group(2)
                    if name == '고정민': continue # 필터링
                    dates = expand_dates(df.columns[c_idx], year)
                    for d in dates:
                        plan_list.append({'name': name, 'date': d.strftime('%Y-%m-%d'), 'plan_ward': match.group(1), 'shift': shift})

    # 2. 실제근무표 분석
    a_sheets = pd.read_excel(up_a, sheet_name=None)
    actual_list = []
    for _, df in a_sheets.items():
        name_idx = next((i for i, c in enumerate(df.columns) if '명' in str(c)), 2)
        day_cols = [i for i, col in enumerate(df.columns) if '일' in str(col)]
        for _, row in df.iterrows():
            name = str(row.iloc[name_idx]).strip()
            # [수정] 고정민 님은 서무 업무자이므로 실적 분석에서 제외
            if name in ['nan', '명', '', '고정민']: continue 
            
            for d_idx in day_cols:
                d_match = re.findall(r'\d+', str(df.columns[d_idx]))
                if not d_match: continue
                day = d_match[0]
                code = str(row.iloc[d_idx])
                if code.startswith('P-'):
                    ward = re.search(r'/(\d+)', code)
                    if ward:
                        actual_list.append({
                            'name': name, 
                            'date': datetime(year, month_val, int(day)).strftime('%Y-%m-%d'), 
                            'actual_ward': str(int(ward.group(1))),
                            'shift': 'D' if 'D' in code else 'E'
                        })

    df_p, df_a = pd.DataFrame(plan_list), pd.DataFrame(actual_list)
    if df_p.empty or df_a.empty: return pd.DataFrame()
    
    merged = pd.merge(df_a, df_p, on=['name', 'date'], how='left', suffixes=('', '_p'))
    merged['status'] = merged.apply(lambda r: "지원(순환)" if r['actual_ward'] == r['plan_ward'] else "결원대체", axis=1)
    return merged

# (나머지 UI 및 알고리즘 코드는 이전과 동일)
