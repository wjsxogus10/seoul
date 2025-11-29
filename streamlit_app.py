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

# 서울시 25개 자치구 리스트
seoul_districts_25 = [
    '강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구', '금천구', '노원구',
    '도봉구', '동대문구', '동작구', '마포구', '서대문구', '서초구', '성동구', '성북구', '송파구',
    '양천구', '영등포구', '용산구', '은평구', '종로구', '중구', '중랑구'
]

# --------------------------------------------------------------------------
# 2. 데이터 로드 및 전처리 (코랩 원본 로직 유지)
# --------------------------------------------------------------------------
@st.cache_data
def load_and_process_all_data():
    dashboard_data_df = pd.DataFrame()
    geojson_data = {}
    gdf_seoul_for_map = geopandas.GeoDataFrame()
    seoul_district_areas_df = pd.DataFrame()

    # -------------------------------------------------------
    # (1) 지도 데이터 로드 (ZIP 또는 SHP 파일 자동 찾기)
    # -------------------------------------------------------
    try:
        # data 폴더 확인
        if not os.path.exists('./data'):
            os.makedirs('./data', exist_ok=True)
            
        # 1순위: zip 파일 찾기, 2순위: shp 파일 찾기
        zip_files = [f for f in os.listdir('./data') if f.endswith('.zip')]
        shp_files = [f for f in os.listdir('./data') if f.endswith('.shp')]
        
        geojso_file_path = None
        if zip_files:
            geojso_file_path = f"zip://./data/{zip_files[0]}" # 첫 번째 zip 파일 사용
        elif shp_files:
            geojso_file_path = f"./data/{shp_files[0]}"      # 첫 번째 shp 파일 사용
            
        if geojso_file_path:
            gdf_seoul = geopandas.read_file(geojso_file_path, encoding='cp949')
            
            # 컬럼명 통일 (SIGUNGU_NM -> 자치구_코드_명)
            col_map = {'SIGUNGU_NM': '자치구_코드_명', 'SIGNGU_NM': '자치구_코드_명'}
            gdf_seoul = gdf_seoul.rename(columns=col_map)
            
            # 자치구명 컬럼이 없는 경우 대비
            if '자치구_코드_명' not in gdf_seoul.columns:
                 # 첫번째 컬럼을 자치구명으로 가정
                 gdf_seoul['자치구_코드_명'] = gdf_seoul.iloc[:, 0]

            gdf_seoul_renamed = gdf_seoul[gdf_seoul.geometry.is_valid].copy()

            gdf_seoul_filtered = gdf_seoul_renamed[
                gdf_seoul_renamed['자치구_코드_명'].isin(seoul_districts_25)
            ].copy()
            
            # dissolve
            gdf_seoul_final_for_merge = gdf_seoul_filtered.dissolve(by='자치구_코드_명', aggfunc='first').reset_index()

            # 면적 계산 (EPSG:5179)
            if gdf_seoul_final_for_merge.crs is None:
                 gdf_seoul_final_for_merge.set_crs(epsg=5179, inplace=True, allow_override=True)
            
            reprojected_gdf_25 = gdf_seoul_final_for_merge.to_crs(epsg=5179)
            reprojected_gdf_25['면적(km²)'] = reprojected_gdf_25.geometry.area / 1_000_000
            seoul_district_areas_df = reprojected_gdf_25[['자치구_코드_명', '면적(km²)']].copy()

            # 지도 표시용 (EPSG:4326)
            gdf_seoul_for_map = gdf_seoul_final_for_merge.to_crs('EPSG:4326')
            geojson_data = gdf_seoul_for_map.__geo_interface__
        else:
            st.error("❌ 'data' 폴더에 지도 파일(.zip 또는 .shp)이 없습니다.")
            return pd.DataFrame(), {}, geopandas.GeoDataFrame()
            
    except Exception as e:
        st.error(f"지리 데이터 로드/처리 중 오류 발생: {e}")
        return pd.DataFrame(), {}, geopandas.GeoDataFrame()

    # -------------------------------------------------------
    # (2) 인구 데이터 로드
    # -------------------------------------------------------
    file_path_population = './data/서울시 상권분석서비스(상주인구-자치구).csv'
    merged_population_density_df = pd.DataFrame()
    
    if os.path.exists(file_path_population):
        try:
            df_population = pd.read_csv(file_path_population, encoding='cp949')
            average_population_by_district = df_population.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
            average_population_by_district['순위'] = average_population_by_district['총_상주인구_수'].rank(ascending=False, method='min').astype(int)

            seoul_population_df = average_population_by_district[
                average_population_by_district['자치구_코드_명'].isin(seoul_districts_25)
            ].copy()
            
            merged_population_density_df = pd.merge(
                seoul_population_df,
                seoul_district_areas_df,
                on='자치구_코드_명',
                how='inner'
            )
            merged_population_density_df['인구_밀도(명/km²)'] = (
                merged_population_density_df['총_상주인구_수'] / merged_population_density_df['면적(km²)' ]
            )
        except Exception as e:
            st.warning(f"인구 데이터 처리 중 오류: {e}")
    else:
        st.warning(f"인구 데이터 파일이 없습니다: {file_path_population}")

    # -------------------------------------------------------
    # (3) 교통 데이터 로드
    # -------------------------------------------------------
    file_path_station_info = './data/GGD_StationInfo_M.xlsx'
    merged_bus_density_df = pd.DataFrame()
    merged_subway_density_df = pd.DataFrame()
    seoul_transport_lacking_df = pd.DataFrame()

    if os.path.exists(file_path_station_info):
        try:
            df_station_info_raw = pd.read_excel(file_path_station_info)
            df_station_info_raw['X'] = pd.to_numeric(df_station_info_raw['X'], errors='coerce')
            df_station_info_raw['Y'] = pd.to_numeric(df_station_info_raw['Y'], errors='coerce')
            df_station_info_raw.dropna(subset=['X', 'Y'], inplace=True)

            geometry_stations = [Point(xy) for xy in zip(df_station_info_raw['X'], df_station_info_raw['Y'])]
            gdf_all_stations = geopandas.GeoDataFrame(df_station_info_raw, geometry=geometry_stations, crs='EPSG:4326')

            gdf_seoul_final_for_merge_reprojected_4326 = gdf_seoul_for_map.to_crs('EPSG:4326')

            all_stations_with_districts = geopandas.sjoin(
                gdf_all_stations,
                gdf_seoul_final_for_merge_reprojected_4326[['자치구_코드_명', 'geometry']],
                how='inner',
                predicate='within'
            )
            seoul_bus_stops_df = all_stations_with_districts.groupby('자치구_코드_명').size().reset_index(name='버스정류장_수')
            seoul_subway_stations_df = all_stations_with_districts.groupby('자치구_코드_명').size().reset_index(name='지하철역_수')

            # 버스 밀도
            merged_bus_density_df = pd.merge(seoul_bus_stops_df, seoul_district_areas_df, on='자치구_코드_명', how='inner')
            merged_bus_density_df['버스정류장_밀도(개/km²)'] = merged_bus_density_df['버스정류장_수'] / merged_bus_density_df['면적(km²)' ]

            # 지하철 밀도
            merged_subway_density_df = pd.merge(seoul_subway_stations_df, seoul_district_areas_df, on='자치구_코드_명', how='inner')
            merged_subway_density_df['지하철역_밀도(개/km²)'] = merged_subway_density_df['지하철역_수'] / merged_subway_density_df['면적(km²)' ]

            # 교통 부족 점수
            seoul_public_transport_counts_df = pd.merge(seoul_bus_stops_df, seoul_subway_stations_df, on='자치구_코드_명', how='outer')
            seoul_public_transport_counts_df['버스정류장_수'] = seoul_public_transport_counts_df['버스정류장_수'].fillna(0).astype(int)
            seoul_public_transport_counts_df['지하철역_수'] = seoul_public_transport_counts_df['지하철역_수'].fillna(0).astype(int)

            seoul_public_transport_counts_df['정류장_부족_순위'] = \
                seoul_public_transport_counts_df['버스정류장_수'].rank(ascending=True, method='min').astype(int)
            seoul_public_transport_counts_df['지하철_부족_순위'] = \
                seoul_public_transport_counts_df['지하철역_수'].rank(ascending=True, method='min').astype(int)
            seoul_public_transport_counts_df['종합_교통_부족_순위'] = \
                seoul_public_transport_counts_df['정류장_부족_순위'] + seoul_public_transport_counts_df['지하철_부족_순위']

            seoul_transport_lacking_df = seoul_public_transport_counts_df[['자치구_코드_명', '정류장_부족_순위', '지하철_부족_순위', '종합_교통_부족_순위']].copy()

        except Exception as e:
            st.warning(f"교통 데이터 처리 중 오류: {e}")
    else:
        st.warning(f"교통 데이터 파일이 없습니다: {file_path_station_info}")

    # -------------------------------------------------------
    # (4) 상권 데이터 로드
    # -------------------------------------------------------
    file_path_commercial = './data/서울시 상권분석서비스(집객시설-자치구).csv'
    seoul_commercial_facilities_df = pd.DataFrame()
    
    if os.path.exists(file_path_commercial):
        try:
            df_stores = pd.read_csv(file_path_commercial, encoding='cp949')
            average_stores_by_district = df_stores.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
            merged_gdf_commercial = gdf_seoul_for_map[['자치구_코드_명']].merge(average_stores_by_district, on='자치구_코드_명', how='left')
            merged_gdf_commercial.dropna(subset=['집객시설_수'], inplace=True)
            merged_gdf_commercial['집객시설_수'] = merged_gdf_commercial['집객시설_수'].astype(int)
            seoul_commercial_facilities_df = merged_gdf_commercial[['자치구_코드_명', '집객시설_수']].copy()
        except Exception as e:
            st.warning(f"상권 데이터 처리 중 오류: {e}")
    else:
        st.warning(f"상권 데이터 파일이 없습니다: {file_path_commercial}")

    # -------------------------------------------------------
    # (5) 최종 데이터 병합
    # -------------------------------------------------------
    if not merged_population_density_df.empty:
        dashboard_data_df = merged_population_density_df[
            ['자치구_코드_명', '총_상주인구_수', '인구_밀도(명/km²)', '면적(km²)']
        ].copy()

        if not merged_bus_density_df.empty:
            dashboard_data_df = pd.merge(
                dashboard_data_df,
                merged_bus_density_df[['자치구_코드_명', '버스정류장_수', '버스정류장_밀도(개/km²)']],
                on='자치구_코드_명',
                how='inner'
            )

        if not merged_subway_density_df.empty:
            dashboard_data_df = pd.merge(
                dashboard_data_df,
                merged_subway_density_df[['자치구_코드_명', '지하철역_수', '지하철역_밀도(개/km²)']],
                on='자치구_코드_명',
                how='inner'
            )

        if not seoul_commercial_facilities_df.empty:
            dashboard_data_df = pd.merge(
                dashboard_data_df,
                seoul_commercial_facilities_df[['자치구_코드_명', '집객시설_수']],
                on='자치구_코드_명',
                how='inner'
            )

        if not seoul_transport_lacking_df.empty:
            dashboard_data_df = pd.merge(
                dashboard_data_df,
                seoul_transport_lacking_df[['자치구_코드_명', '정류장_부족_순위', '지하철_부족_순위', '종합_교통_부족_순위']],
                on='자치구_코드_명',
                how='inner'
            )
    else:
        st.error("핵심 데이터(인구 데이터)가 로드되지 않아 대시보드를 구성할 수 없습니다.")
        dashboard_data_df = pd.DataFrame()

    return dashboard_data_df, geojson_data, gdf_seoul_for_map

# --------------------------------------------------------------------------
# 3. Streamlit 화면 구성 (여기가 실제 보여지는 부분)
# --------------------------------------------------------------------------

# 데이터 로드
dashboard_data_df, geojson_data, gdf_seoul_for_map = load_and_process_all_data()

st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")
st.markdown("서울시 25개 자치구의 **인구, 상업시설, 버스/지하철 인프라** 데이터를 통합 분석합니다.")

if not dashboard_data_df.empty:
    # --- 옵션 선택 ---
    col1, col2 = st.columns(2)
    with col1:
        selected_district = st.selectbox(
            "자치구 선택:",
            options=['전체 구'] + sorted(dashboard_data_df['자치구_코드_명'].unique().tolist())
        )
    with col2:
        # 지도에 표시할 컬럼 매핑
        metric_options_map = {
            '인구 밀도 (명/km²)': '인구_밀도(명/km²)',
            '집객시설 수': '집객시설_수',
            '버스정류장 밀도 (개/km²)': '버스정류장_밀도(개/km²)',
            '지하철역 밀도 (개/km²)': '지하철역_밀도(개/km²)',
            '종합 교통 부족 순위 (높을수록 부족)': '종합_교통_부족_순위'
        }
        # 데이터프레임에 실제로 있는 컬럼만 필터링
        available_metrics = {k: v for k, v in metric_options_map.items() if v in dashboard_data_df.columns}
        
        selected_metric_display = st.selectbox(
            "지도/차트 분석 지표:",
            options=list(available_metrics.keys())
        )
        selected_metric = available_metrics[selected_metric_display]

    st.markdown("---")

    # --- 지도 시각화 ---
    st.subheader(f"🗺️ 서울시 자치구별 {selected_metric_display}")

    filtered_df = dashboard_data_df.copy()
    if selected_district != '전체 구':
        filtered_df = filtered_df[filtered_df['자치구_코드_명'] == selected_district]

    # 지도 중심점 및 줌 설정
    center_lat, center_lon = 37.5665, 126.9780
    zoom_level = 9.5
    
    if selected_district != '전체 구' and not gdf_seoul_for_map.empty:
         dist_geo = gdf_seoul_for_map[gdf_seoul_for_map['자치구_코드_명'] == selected_district]
         if not dist_geo.empty:
             center_lat = dist_geo.geometry.centroid.y.values[0]
             center_lon = dist_geo.geometry.centroid.x.values[0]
             zoom_level = 11.5

    # 색상 스케일 설정 (교통 부족 순위는 빨간색일수록 안 좋음)
    colorscale = 'YlGnBu'
    if '부족_순위' in selected_metric:
        colorscale = 'YlOrRd'

    fig_map = px.choropleth_mapbox(
        dashboard_data_df, # 전체 데이터를 써야 색상 비교가 됨
        geojson=geojson_data,
        locations='자치구_코드_명',
        featureidkey='properties.자치구_코드_명',
        color=selected_metric,
        color_continuous_scale=colorscale,
        mapbox_style="carto-positron",
        zoom=zoom_level,
        center={"lat": center_lat, "lon": center_lon},
        opacity=0.7,
        hover_name='자치구_코드_명',
        hover_data=list(available_metrics.values())
    )
    fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=600)
    st.plotly_chart(fig_map, use_container_width=True)

    # --- 차트 시각화 ---
    st.markdown("---")
    st.subheader("📊 순위 비교 분석")
    
    col3, col4 = st.columns(2)
    with col3:
        chart_type = st.radio("정렬 기준:", ['상위 10개', '하위 10개'], horizontal=True)
    
    ascending = True if chart_type == '하위 10개' else False
    sorted_df = dashboard_data_df.sort_values(by=selected_metric, ascending=ascending).head(10)
    
    fig_bar = px.bar(
        sorted_df,
        x='자치구_코드_명',
        y=selected_metric,
        title=f"{selected_metric_display} {chart_type}",
        color=selected_metric,
        color_continuous_scale=colorscale
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- 데이터 표 ---
    with st.expander("📋 전체 데이터 상세 보기"):
        st.dataframe(dashboard_data_df)

else:
    st.info("데이터 로드를 기다리고 있습니다...")
