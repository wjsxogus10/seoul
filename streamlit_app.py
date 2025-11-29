import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import os

# --------------------------------------------------------------------------
# 1. 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")

# --------------------------------------------------------------------------
# 2. 스마트 데이터 로드 함수 (파일 이름 자동 찾기)
# --------------------------------------------------------------------------
@st.cache_data
def load_data():
    # 1. 지도 파일(.shp) 자동 찾기
    if not os.path.exists('./data'):
        st.error("❌ 'data' 폴더가 없습니다. 깃허브에 폴더가 올라갔는지 확인해주세요.")
        return None, None

    # data 폴더 안에 있는 파일 중 .shp로 끝나는 것 찾기
    shp_files = [f for f in os.listdir('./data') if f.endswith('.shp')]
    
    if not shp_files:
        st.error("❌ 'data' 폴더 안에 .shp 파일이 없습니다.")
        st.write("현재 data 폴더 내용:", os.listdir('./data'))
        return None, None
    
    # 첫 번째 발견된 지도 파일 선택
    target_shp = os.path.join('./data', shp_files[0])
    
    try:
        # 지도 읽기
        gdf = geopandas.read_file(target_shp, encoding='cp949')
        
        # 좌표계 변환 (WGS84: 지도 표시용)
        if gdf.crs is None:
            gdf.set_crs(epsg=5179, inplace=True, allow_override=True)
        gdf = gdf.to_crs(epsg=4326)
        
        # 컬럼 이름 통일 (자치구 이름 찾기)
        # 보통 SIGUNGU_NM, SIGNGU_NM, L10100 등 다양함 -> 'name'으로 통일
        possible_name_cols = ['SIGUNGU_NM', 'SIGNGU_NM', 'L10100', 'name', 'NAME']
        found_col = None
        for col in possible_name_cols:
            if col in gdf.columns:
                found_col = col
                break
        
        if found_col:
            gdf = gdf.rename(columns={found_col: '자치구명'})
        else:
            # 컬럼을 못 찾으면 첫 번째 컬럼을 이름으로 가정
            gdf['자치구명'] = gdf.iloc[:, 0]

        return gdf, shp_files[0] # 데이터와 파일명 반환

    except Exception as e:
        st.error(f"지도를 읽는 도중 오류가 났습니다: {e}")
        return None, None

# --------------------------------------------------------------------------
# 3. 화면 표시
# --------------------------------------------------------------------------
gdf, filename = load_data()

if gdf is not None:
    st.success(f"✅ 지도 파일 로드 성공! (파일명: {filename})")
    
    # 지도 시각화
    st.subheader("🗺️ 서울시 자치구 지도")
    
    # 중심점 계산
    center_lat = gdf.geometry.centroid.y.mean()
    center_lon = gdf.geometry.centroid.x.mean()
    
    # 지도 그리기
    fig = px.choropleth_mapbox(
        gdf,
        geojson=gdf.geometry.__geo_interface__,
        locations=gdf.index, # 인덱스 기준 매핑
        color='자치구명', # 색상 구분 기준
        mapbox_style="carto-positron",
        zoom=10,
        center={"lat": center_lat, "lon": center_lon},
        opacity=0.5,
        title=f"사용된 파일: {filename}"
    )
    fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0}, height=600)
    st.plotly_chart(fig, use_container_width=True)

    # 데이터 미리보기
    with st.expander("📊 지도 데이터 원본 보기"):
        st.dataframe(gdf.drop(columns='geometry').head())

else:
    st.warning("데이터를 불러오지 못해 지도를 그릴 수 없습니다.")
