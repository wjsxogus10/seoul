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
    # 1. 지도 데이터 로드 (공공 데이터 URL 사용 - 가장 안정적)
    # -----------------------------------------------------------
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326)
        
        # 컬럼명 통일 ('자치구명'으로 변경)
        if 'name' in gdf.columns:
            gdf = gdf.rename(columns={'name': '자치구명'})
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf = gdf.rename(columns={'SIG_KOR_NM': '자치구명'})
            
        # 면적 계산 (도형 넓이 기반, 근사값)
        gdf_area = gdf.to_crs(epsg=5179) # 면적 계산용 좌표계
        gdf['면적(km²)'] = gdf_area.geometry.area / 1_000_000
        
    except Exception as e:
        st.error(f"지도를 불러오는 중 오류 발생: {e}")
        return None

    # -----------------------------------------------------------
    # 2. 사용자 데이터 로드 및 병합
    # -----------------------------------------------------------
    
    # (A) 인구 데이터
    pop_file = './data/서울시 상권분석서비스(상주인구-자치구).csv'
    if os.path.exists(pop_file):
        try:
            df_pop = pd.read_csv(pop_file, encoding='cp949')
            # 자치구별 평균 상주인구 계산
            df_pop_group = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
            df_pop_group.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
            
            # 지도에 병합
            gdf = gdf.merge(df_pop_group, on='자치구명', how='left')
            # 인구 밀도 계산
            gdf['인구_밀도(명/km²)'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
            
        except Exception as e:
            st.warning(f"인구 데이터를 읽는 중 오류: {e}")
    else:
        st.info("ℹ️ 인구 데이터 파일이 없습니다. (지도만 표시됩니다)")

    # (B) 상권(집객시설) 데이터
    biz_file = './data/서울시 상권분석서비스(집객시설-자치구).csv'
    if os.path.exists(biz_file):
        try:
            df_biz = pd.read_csv(biz_file, encoding='cp949')
            df_biz_group = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
            df_biz_group.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
            
            gdf = gdf.merge(df_biz_group, on='자치구명', how='left')
        except Exception as e:
            st.warning(f"상권 데이터를 읽는 중 오류: {e}")

    # (C) 교통(정류장) 데이터 - 분석 로직
    station_file = './data/GGD_StationInfo_M.xlsx'
    if os.path.exists(station_file):
        try:
            df_station = pd.read_excel(station_file)
            # 좌표가 있는 데이터만 필터링
            df_station = df_station.dropna(subset=['X', 'Y'])
            
            # 정류장 위치를 지도 좌표로 변환
            geometry = [Point(xy) for xy in zip(df_station['X'], df_station['Y'])]
            gdf_station = geopandas.GeoDataFrame(df_station, geometry=geometry, crs="EPSG:4326")
            
            # 공간 조인 (어느 구에 정류장이 있는지 매칭)
            joined = geopandas.sjoin(gdf_station, gdf, how="inner", predicate="within")
            
            # 구별 정류장 개수 세기
            station_counts = joined.groupby('자치구명').size().reset_index(name='정류장_수')
            
            gdf = gdf.merge(station_counts, on='자치구명', how='left')
            gdf['정류장_밀도(개/km²)'] = gdf['정류장_수'] / gdf['면적(km²)']
            
        except Exception as e:
            st.warning(f"교통 데이터를 분석하는 중 오류: {e}")

    return gdf

# -----------------------------------------------------------
# 3. 대시보드 화면 구성
# -----------------------------------------------------------
gdf = load_and_merge_data()

if gdf is not None:
    # 사이드바에서 보고 싶은 데이터 선택
    metrics = {
        '면적(km²)': '면적(km²)',
        '총 상주인구': '총_상주인구_수',
        '인구 밀도': '인구_밀도(명/km²)',
        '집객시설 수': '집객시설_수',
        '정류장 수': '정류장_수',
        '정류장 밀도': '정류장_밀도(개/km²)'
    }
    
    # 데이터가 있는 컬럼만 필터링
    available_metrics = {k: v for k, v in metrics.items() if v in gdf.columns}
    
    if available_metrics:
        selected_metric_name = st.sidebar.selectbox("보고 싶은 데이터를 선택하세요", list(available_metrics.keys()))
        selected_col = available_metrics[selected_metric_name]
        
        st.subheader(f"🗺️ 서울시 {selected_metric_name} 현황")
        
        # 지도 시각화
        center_lat = gdf.geometry.centroid.y.mean()
        center_lon = gdf.geometry.centroid.x.mean()
        
        fig = px.choropleth_mapbox(
            gdf,
            geojson=gdf.geometry.__geo_interface__,
            locations=gdf.index,
            color=selected_col,
            mapbox_style="carto-positron",
            zoom=10,
            center={"lat": center_lat, "lon": center_lon},
            opacity=0.6,
            hover_data=['자치구명'] + list(available_metrics.values())
        )
        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=600)
        st.plotly_chart(fig, use_container_width=True)
        
        # 하단 데이터 표
        with st.expander("📊 상세 데이터 표 보기"):
            display_cols = ['자치구명'] + list(available_metrics.values())
            st.dataframe(gdf[display_cols].sort_values(by=selected_col, ascending=False))
            
    else:
        st.warning("지도 파일은 로드되었으나, 분석할 데이터 파일(csv/xlsx)이 없어 기본 지도만 표시합니다.")
        st.info("data 폴더에 분석 데이터를 업로드하면 자동으로 합쳐집니다!")
