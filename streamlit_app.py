import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import os

st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")

@st.cache_data
def load_data():
    # -----------------------------------------------------------
    # ⭐ [핵심] 파일 업로드 없이, 인터넷 주소에서 바로 가져옵니다!
    # 서울시 자치구 경계 (GitHub에 공개된 공공 데이터 사용)
    # -----------------------------------------------------------
    url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    
    try:
        # 인터넷에서 읽어오기
        gdf = geopandas.read_file(url)
        
        # 좌표계 설정 (이미 위도/경도로 되어 있어서 4326으로 지정)
        gdf = gdf.to_crs(epsg=4326)
        
        # 컬럼 이름 통일 ('name' 컬럼을 '자치구명'으로 변경)
        # 공공 데이터에는 보통 'name', 'name_eng' 등이 들어있습니다.
        if 'name' in gdf.columns:
            gdf = gdf.rename(columns={'name': '자치구명'})
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf = gdf.rename(columns={'SIG_KOR_NM': '자치구명'})
            
        return gdf

    except Exception as e:
        st.error(f"지도를 가져오는 중 오류가 났습니다: {e}")
        return None

# 실행 및 시각화
gdf = load_data()

if gdf is not None:
    st.success("✅ 서울시 지도 로드 성공! (공공 데이터 URL 사용)")
    
    # 중심점 계산
    center_lat = gdf.geometry.centroid.y.mean()
    center_lon = gdf.geometry.centroid.x.mean()
    
    # 지도 그리기
    fig = px.choropleth_mapbox(
        gdf,
        geojson=gdf.geometry.__geo_interface__,
        locations=gdf.index,
        color='자치구명',
        mapbox_style="carto-positron",
        zoom=10,
        center={"lat": center_lat, "lon": center_lon},
        opacity=0.5,
        title="서울시 자치구 현황"
    )
    fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0}, height=600)
    st.plotly_chart(fig, use_container_width=True)
    
    with st.expander("데이터 원본 보기"):
        st.dataframe(gdf.drop(columns='geometry').head())
