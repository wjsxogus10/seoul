import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import os

st.set_page_config(layout="wide", page_title="오류 진단 모드")
st.title("🛠️ 대시보드 오류 진단 모드")

# 1. 라이브러리 확인
st.write("### 1. 환경 점검")
try:
    import geopandas
    st.success("✅ Geopandas 설치됨 (지도를 그릴 수 있음)")
except ImportError:
    st.error("❌ Geopandas가 설치되지 않았습니다. requirements.txt에 'geopandas'를 추가하세요.")

try:
    import openpyxl
    st.success("✅ Openpyxl 설치됨 (엑셀을 읽을 수 있음)")
except ImportError:
    st.error("❌ Openpyxl이 설치되지 않았습니다. requirements.txt에 'openpyxl'을 추가하세요.")

# 2. 파일 확인
st.write("### 2. data 폴더 파일 확인")
if os.path.exists('./data'):
    files = os.listdir('./data')
    st.info(f"📂 발견된 파일 목록: {files}")
    
    # 필수 파일 체크
    required_files = [
        '서울시 상권분석서비스(상주인구-자치구).csv',
        '서울시 상권분석서비스(집객시설-자치구).csv',
        'GGD_StationInfo_M.xlsx',
        'seoul_subway_density.xlsx'
    ]
    
    for f in required_files:
        if f in files:
            st.success(f"✅ 파일 있음: {f}")
        else:
            st.error(f"❌ 파일 없음: {f} (이름이 정확한지 확인하세요!)")
else:
    st.error("❌ 'data' 폴더가 아예 없습니다! 깃허브에 폴더가 올라갔는지 확인하세요.")

# 3. 데이터 로드 테스트
st.write("### 3. 데이터 로드 테스트")

# 지하철 파일 테스트
subway_file = './data/seoul_subway_density.xlsx - Sheet1.csv'
if os.path.exists(subway_file):
    try:
        try:
            df = pd.read_csv(subway_file, encoding='utf-8')
        except:
            df = pd.read_csv(subway_file, encoding='cp949')
        st.write("📄 지하철 파일 미리보기:", df.head(3))
        st.write("데이터 컬럼명:", df.columns.tolist())
    except Exception as e:
        st.error(f"지하철 파일 읽기 실패: {e}")

# 지도 테스트
try:
    url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    gdf = geopandas.read_file(url)
    st.success("✅ 지도 데이터(GeoJSON) 다운로드 성공!")
except Exception as e:
    st.error(f"❌ 지도 다운로드 실패: {e}")

