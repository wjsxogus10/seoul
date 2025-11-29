import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import os
from shapely.geometry import Point

# --------------------------------------------------------------------------
# 2. 데이터 로드 및 병합 함수 (Safe Mode: ONLY Loads Map)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="1. 기본 지도를 다운로드하고 있습니다...")
def load_and_merge_data_safe_mode():
    
    # 1. 지도 데이터 로드 (GeoJSON - 외부 URL)
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326)
        
        # '자치구명' 컬럼 생성 (KeyError 방지)
        if 'name' in gdf.columns:
            gdf['자치구명'] = gdf['name']
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf['자치구명'] = gdf['SIG_KOR_NM']
        else:
            return None # 자치구 컬럼 없으면 실패 처리
            
        gdf['면적(km²)'] = gdf.geometry.to_crs(epsg=5179).area / 1_000_000
    except Exception as e:
        return None # 지도 로드 실패

    # 2. 필수 컬럼 초기화 (나머지 로직을 위해 빈 컬럼은 유지)
    cols_to_init = ['총_상주인구_수', '인구 밀도', '집객시설 수', '버스정류장_수', '버스정류장 밀도', '지하철역_수', '지하철역 밀도', '총_교통수단_수', '대중교통 밀도', '교통 부족 순위']
    for c in cols_to_init:
        if c not in gdf.columns:
            gdf[c] = 0
            
    # 빈 DataFrame 리턴 (Subway Coordinates)
    df_stations = pd.DataFrame()

    return gdf, df_stations

# --------------------------------------------------------------------------
# 3. 화면 구성 및 진단
# --------------------------------------------------------------------------
result = load_and_merge_data_safe_mode()

if result is None or result[0] is None:
    st.error("❌ GeoJSON 지도 파일을 로드하지 못했습니다. (라이브러리 또는 네트워크 문제)")
    st.info("💡 만약 이 상태가 지속되면, Geopandas 라이브러리 설치 문제일 수 있습니다.")
    st.stop()

gdf, df_stations = result
st.success("✅ Safe Mode 성공! 기본 지도가 로드되었습니다.")
st.write("---")

st.sidebar.header("🔍 분석 옵션")
st.sidebar.write("현재 Safe Mode에서는 지도만 표시됩니다.")

# Map display logic (simplified)
st.subheader("🗺️ 서울시 기본 지도")

fig_map = px.choropleth_mapbox(
    gdf, 
    geojson=gdf.geometry.__geo_interface__, 
    locations=gdf.index,
    color='자치구명', # 자치구 이름을 색상으로 사용
    mapbox_style="carto-positron", 
    zoom=9.5,
    center={"lat": 37.5665, "lon": 126.9780}, 
    opacity=0.7,
    hover_name='자치구명'
)

fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
st.plotly_chart(fig_map, use_container_width=True)
st.dataframe(gdf[['자치구명', '면적(km²)']].head())
