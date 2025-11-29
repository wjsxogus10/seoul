import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import os

# --------------------------------------------------------------------------
# 1. 페이지 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="환경 안정성 진단")
st.title("🛠️ 최종 환경 안정성 진단 모드")

# --------------------------------------------------------------------------
# 2. 지도 로드 테스트 (GeoPandas Only)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="GeoJSON 지도 파일을 다운로드 중...")
def load_base_map_only():
    # 외부 GeoJSON URL
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        # GeoPandas가 네트워크에서 파일을 읽고 GeoDataFrame을 생성하는지 테스트
        gdf = geopandas.read_file(map_url)
        
        # 최소한의 컬럼만 생성 (에러 방지)
        if 'name' in gdf.columns:
             gdf['자치구명'] = gdf['name']
        
        return gdf
    except Exception as e:
        # 실패 시 에러 리턴
        st.error(f"❌ 지도 로드 중 치명적 오류 발생: {e}")
        return None

# --------------------------------------------------------------------------
# 3. 화면 표시
# --------------------------------------------------------------------------
gdf = load_base_map_only()

if gdf is not None and not gdf.empty:
    st.success("✅ 환경 안정성 테스트 성공: GeoJSON 지도 파일을 성공적으로 읽었습니다.")
    st.info("💡 문제 없음. 이제 모든 파일 로드 코드를 다시 붙여넣고 재시도해주세요.")
    
    # 지도 표시 (성공 확인용)
    fig = px.choropleth_mapbox(
        gdf, 
        geojson=gdf.geometry.__geo_interface__, 
        locations=gdf.index,
        color='자치구명', 
        mapbox_style="carto-positron", 
        zoom=9.5,
        center={"lat": 37.5665, "lon": 126.9780}, 
        opacity=0.7,
        hover_name='자치구명'
    )
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("❌ GeoPandas 환경이 불안정하거나 GeoJSON 로드에 실패했습니다. (GDAL/GEOS 문제)")
