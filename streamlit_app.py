import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import numpy as np
from shapely.geometry import Point
import os

# 1. 한글 폰트 설정 (깨짐 방지)
st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")

# 2. 데이터 로드 함수
@st.cache_data
def load_data():
    # 데이터가 없으면 빈 껍데기만 보여주도록 예외처리
    return pd.DataFrame()

# 3. 메인 화면 구성
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")
st.write("데이터가 정상적으로 로드되면 이곳에 지도가 표시됩니다.")

# 4. 파일 경로 확인용 (디버깅)
st.write("현재 폴더의 파일 목록:", os.listdir('.'))
if os.path.exists('./data'):
    st.write("data 폴더 내부:", os.listdir('./data'))
else:
    st.error("data 폴더가 없습니다! 깃허브에 폴더째로 올렸는지 확인해주세요.")
