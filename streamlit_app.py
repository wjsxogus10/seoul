import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import numpy as np
from shapely.geometry import Point
import os

# --------------------------------------------------------------------------
# 1. 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")

# --------------------------------------------------------------------------
# 2. 데이터 로드 함수
# --------------------------------------------------------------------------
@st.cache_data
def load_and_process_all_data():
    # 빈 데이터프레임 미리 생성 (에러 방지용)
    dashboard_data_df = pd.DataFrame()
    geojson_data = {}
    gdf_seoul_for_map = geopandas.GeoDataFrame()

    # (1) 지도 데이터 로드 (shp)
    try:
        # 사진에 있는 파일명(TN_SIGNGU_BNDRY)으로 시도해보고, 없으면 원래 이름으로 시도
        possible_files = [
            './data/TN_SIGNGU_BNDRY.shp',  # 고객님 스크린샷에 보이는 파일
            './data/BND_SIGUNGU_PG.shp'    # 원래 준비했던 파일
        ]
        
        geojso_file_path = None
        for f in possible_files:
            if os.path.exists(f):
                geojso_file_path = f
                break
        
        if geojso_file_path is None:
            st.error("지도 파일(.shp)을 찾을 수 없습니다. data 폴더를 확인해주세요.")
            return pd.DataFrame(), {}, geopandas.GeoDataFrame()

        gdf_seoul = geopandas.read_file(geojso_file_path, encoding='cp949')
        
        # 컬럼 이름 통일 (SIGUNGU_NM -> 자치구_코드_명)
        # 만약 파일마다 컬럼명이 다를 수 있어 확인 필요
        col_map = {'SIGUNGU_NM': '자치구_코드_명', 'SIGNGU_NM': '자치구_코드_명'}
        gdf_seoul = gdf_seoul.rename(columns=col_map)
        
        # 좌표계 변환 및 면적 계산
        if not gdf_seoul.empty:
             # 서울 25개 구만 필터링하기 위해 리스트 정의
            seoul_districts_25 = [
                '강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구', '금천구', '노원구',
                '도봉구', '동대문구', '동작구', '마포구', '서대문구', '서초구', '성동구', '성북구', '송파구',
                '양천구', '영등포구', '용산구', '은평구', '종로구', '중구', '중랑구'
            ]
            
            # 자치구명 컬럼이 있는지 확인
            if '자치구_코드_명' in gdf_seoul.columns:
                 gdf_seoul = gdf_seoul[gdf_seoul['자치구_코드_명'].isin(seoul_districts_25)].copy()
            
            # 좌표계 변환 (지도 표시용 4326, 면적 계산용 5179)
            if gdf_seoul.crs is None:
                 gdf_seoul.set_crs(epsg=5179, inplace=True, allow_override=True)
            
            gdf_seoul_for_map = gdf_seoul.to_crs(epsg=4326)
            geojson_data = gdf_seoul_for_map.__geo_interface__
            
            # 면적 계산을 위한 데이터프레임
            gdf_area = gdf_seoul.to_crs(epsg=5179)
            gdf_area['면적(km²)'] = gdf_area.geometry.area / 1_000_000
            seoul_district_areas_df = gdf_area[['자치구_코드_명', '면적(km²)']].copy() if '자치구_코드_명' in gdf_area.columns else pd.DataFrame()

    except Exception as e:
        st.error(f"지도 데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame(), {}, geopandas.GeoDataFrame()

    # (2) 인구, 교통, 상권 데이터 로드 (파일이 없으면 경고만 띄우고 넘어감)
    try:
        # 인구
        if os.path.exists('./data/서울시 상권분석서비스(상주인구-자치구).csv'):
            df_pop = pd.read_csv('./data/서울시 상권분석서비스(상주인구-자치구).csv', encoding='cp949')
            # (데이터 전처리 로직 간소화하여 병합)
            # 여기서는 예시로 간단하게 처리하거나, 실제 로직을 다 넣어야 함.
            # 일단 지도가 뜨는게 우선이므로, 데이터 프레임을 지도 데이터 기준으로 생성
            if not seoul_district_areas_df.empty:
                 dashboard_data_df = seoul_district_areas_df.copy()
                 # 임시 데이터 채우기 (파일 로드 로직이 복잡하여, 일단 지도 표시 우선)
                 dashboard_data_df['인구_밀도(명/km²)'] = 0 
        else:
            st.warning("인구 데이터 파일이 없습니다.")
            if not seoul_district_areas_df.empty:
                dashboard_data_df = seoul_district_areas_df.copy()

    except Exception as e:
        st.warning(f"추가 데이터 로드 중 오류: {e}")

    return dashboard_data_df, geojson_data, gdf_seoul_for_map

# --------------------------------------------------------------------------
# 3. 데이터 실행 및 시각화
# --------------------------------------------------------------------------
dashboard_data_df, geojson_data, gdf_seoul_for_map = load_and_process_all_data()

if not gdf_seoul_for_map.empty:
    st.subheader("🗺️ 서울시 지도 시각화")
    
    # 지도 그리기
    center_lat, center_lon = 37.5665, 126.9780
    
    # 색상 기준 컬럼 (데이터가 없으면 임의로 설정)
    color_col = '면적(km²)' if '면적(km²)' in gdf_seoul_for_map.columns else None

    if color_col:
        fig = px.choropleth_mapbox(
            gdf_seoul_for_map,
            geojson=geojson_data,
            locations='자치구_코드_명',
            featureidkey='properties.자치구_코드_명',
            color=color_col,
            mapbox_style="carto-positron",
            zoom=9.5,
            center={"lat": center_lat, "lon": center_lon},
            opacity=0.6,
            title="서울시 자치구별 면적 (테스트)"
        )
        fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("지도는 로드되었으나 표시할 데이터 컬럼이 없습니다.")
        st.write(gdf_seoul_for_map.head())
else:
    st.info("지도를 불러오는 중이거나 데이터가 부족합니다.")
