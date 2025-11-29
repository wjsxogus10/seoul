import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide", page_title="오류 진단")
st.title("🛠️ 대시보드 오류 진단 모드")

st.write("### 1. 라이브러리 설치 확인")

# 1. Geopandas 확인
try:
    import geopandas
    st.success("✅ Geopandas 설치됨 (지도 그리기 가능)")
except ImportError:
    st.error("❌ Geopandas가 없습니다! requirements.txt에 'geopandas'를 추가하세요.")

# 2. Openpyxl 확인
try:
    import openpyxl
    st.success("✅ Openpyxl 설치됨 (엑셀 읽기 가능)")
except ImportError:
    st.error("❌ Openpyxl이 없습니다! requirements.txt에 'openpyxl'을 추가하세요.")

st.write("### 2. 데이터 파일 확인")
if os.path.exists('./data'):
    files = os.listdir('./data')
    st.info(f"📂 현재 data 폴더에 있는 파일들: {files}")
    
    # 핵심 파일 체크
    target_file = 'seoul_subway_density.xlsx - Sheet1.csv'
    if target_file in files:
        st.success(f"✅ 지하철 밀도 파일 있음: {target_file}")
        
        # 파일 읽기 테스트
        try:
            df = pd.read_csv(f'./data/{target_file}')
            st.write("📄 파일 내용 미리보기:", df.head(3))
        except Exception as e:
            st.error(f"❌ 파일은 있는데 읽을 수가 없습니다. 에러 내용: {e}")
    else:
        st.error(f"❌ '{target_file}' 파일이 없습니다. 파일 이름을 확인해주세요!")
else:
    st.error("❌ 'data' 폴더가 아예 없습니다.")

st.write("### 3. 지도 다운로드 테스트")
try:
    import geopandas
    url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    gdf = geopandas.read_file(url)
    st.success(f"✅ 지도 데이터 다운로드 성공! (구 개수: {len(gdf)}개)")
except Exception as e:
    st.error(f"❌ 지도 다운로드 실패: {e}")
