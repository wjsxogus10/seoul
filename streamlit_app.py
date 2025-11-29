import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide", page_title="데이터 타입 진단 모드")
st.title("🛠️ 지하철 밀도 데이터 타입 확인")

def check_subway_data_integrity():
    st.info("💡 지하철 밀도 파일을 읽고 컬럼 타입을 확인합니다.")
    
    file_name = '지하철 밀도.CSV'
    file_path = f'./data/{file_name}'
    
    if not os.path.exists(file_path):
        st.error(f"❌ '{file_name}' 파일을 찾을 수 없습니다. 이름 확인해주세요.")
        return
        
    try:
        # 1. 파일 읽기 (인코딩 자동 감지 시도)
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except:
            df = pd.read_csv(file_path, encoding='cp949')

        st.success(f"✅ 파일 로드 성공: {file_name}")
        
        # 2. 컬럼에서 '밀도'와 '자치구' 찾기
        density_col = next((c for c in df.columns if '밀도' in c), None)
        gu_col = next((c for c in df.columns if '자치구' in c), None)
        
        if not density_col:
            st.error("❌ '밀도' 컬럼을 찾을 수 없습니다.")
            return

        st.write("### 진단 결과")
        st.dataframe(df.dtypes.reset_index().rename(columns={'index': '컬럼명', 0: '타입'}))
        
        # 3. 밀도 컬럼 타입 확인
        density_dtype = df[density_col].dtype
        
        if density_dtype == object:
            st.error(f"🚨 치명적 오류: '{density_col}' 컬럼이 '문자열(object)'로 읽힙니다.")
            st.info("💡 해결 방법: 엑셀에서 쉼표(,)나 숨겨진 공백을 제거하고 숫자로 저장해야 합니다.")
        else:
            st.success(f"✅ 타입 정상: '{density_col}' 컬럼이 '{density_dtype}'로 읽힙니다. (성공)")

    except Exception as e:
        st.error(f"❌ 파일 읽기 중 알 수 없는 오류 발생: {e}")

check_subway_data_integrity()
