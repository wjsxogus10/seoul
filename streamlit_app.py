import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import os
from shapely.geometry import Point

st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")

@st.cache_data
def load_and_merge_data():
    # -----------------------------------------------------------
    # 1. 지도 데이터 (인터넷 공공 데이터)
    # -----------------------------------------------------------
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326)
        
        # 컬럼 통일
        col_map = {'name': '자치구명', 'SIG_KOR_NM': '자치구명'}
        gdf = gdf.rename(columns=col_map)
        
        # 면적 계산
        gdf_area = gdf.to_crs(epsg=5179)
        gdf['면적(km²)'] = gdf_area.geometry.area / 1_000_000
    except Exception as e:
        st.error(f"지도 로드 실패: {e}")
        return None

    # -----------------------------------------------------------
    # 2. 사용자 데이터 병합
    # -----------------------------------------------------------
    
    # (A) 인구 데이터
    pop_file = './data/서울시 상권분석서비스(상주인구-자치구).csv'
    if os.path.exists(pop_file):
        try:
            df_pop = pd.read_csv(pop_file, encoding='cp949')
            df_grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
            df_grp.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
            gdf = gdf.merge(df_grp, on='자치구명', how='left')
            gdf['인구_밀도(명/km²)'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
        except: pass

    # (B) 상권 데이터
    biz_file = './data/서울시 상권분석서비스(집객시설-자치구).csv'
    if os.path.exists(biz_file):
        try:
            df_biz = pd.read_csv(biz_file, encoding='cp949')
            df_grp = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
            df_grp.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
            gdf = gdf.merge(df_grp, on='자치구명', how='left')
        except: pass

    # (C) 버스 정류장 데이터 (GGD_StationInfo_M.xlsx)
    bus_file = './data/GGD_StationInfo_M.xlsx'
    if os.path.exists(bus_file):
        try:
            df = pd.read_excel(bus_file)
            df = df.dropna(subset=['X', 'Y'])
            # 좌표 변환 및 매칭
            geom = [Point(xy) for xy in zip(df['X'], df['Y'])]
            gdf_bus = geopandas.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")
            joined = geopandas.sjoin(gdf_bus, gdf, how="inner", predicate="within")
            
            # 집계
            cnt = joined.groupby('자치구명').size().reset_index(name='버스정류장_수')
            gdf = gdf.merge(cnt, on='자치구명', how='left')
            gdf['버스정류장_수'] = gdf['버스정류장_수'].fillna(0)
            gdf['버스정류장_밀도(개/km²)'] = gdf['버스정류장_수'] / gdf['면적(km²)']
        except: pass
