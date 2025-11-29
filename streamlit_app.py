import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import os

st.set_page_config(layout="wide", page_title="오류 진단 모드")
st.title("🚨 상세 오류 진단 모드")

st.write("### 1. 기본 환경 점검")
st.write(f"- 현재 위치: `{os.getcwd()}`")

if os.path.exists('./data'):
    st.write(f"- data 폴더 파일 목록: {os.listdir('./data')}")
else:
    st.error("❌ 'data' 폴더가 없습니다! (GitHub에 폴더가 안 올라갔을 수 있습니다)")

st.write("---")
st.write("### 2. 지도 데이터(GeoJSON) 로드 테스트")

map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"

try:
    with st.spinner("지도 데이터를 다운로드 중입니다..."):
        gdf = geopandas.read_file(map_url)
        st.success(f"✅ 지도 로드 성공! (총 {len(gdf)}개 자치구)")
        st.write(gdf.head(3))
except Exception as e:
    st.error("❌ 지도 로드 실패!")
    st.error(f"에러 내용: {e}") # <--- 이 내용이 중요합니다!
    st.stop()

st.write("---")
st.write("### 3. 지하철 데이터 로드 테스트")

density_file = './data/지하철 밀도.CSV'
if os.path.exists(density_file):
    try:
        try: df = pd.read_csv(density_file, encoding='utf-8')
        except: df = pd.read_csv(density_file, encoding='cp949')
        st.success("✅ 지하철 밀도 파일 읽기 성공")
        st.write("컬럼 목록:", df.columns.tolist())
    except Exception as e:
        st.error(f"❌ 지하철 파일 읽기 실패: {e}")
else:
    st.warning("⚠️ 지하철 밀도 파일이 없습니다.")

st.info("이 화면을 캡처해서 보여주세요. 빨간색 에러 메시지가 해결의 열쇠입니다.")
