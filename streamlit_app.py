import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import os
from shapely.geometry import Point

# --------------------------------------------------------------------------
# 1. 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")

# --------------------------------------------------------------------------
# 2. 데이터 로드 및 병합 함수
# --------------------------------------------------------------------------
@st.cache_data
def load_and_merge_data():
    # -----------------------------------------------------------
    # [핵심] 지도 파일 업로드 없이, 인터넷 주소에서 바로 가져옵니다!
    # -----------------------------------------------------------
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    
    try:
        # 인터넷에서 지도 읽기
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326) # 지도 표시용 좌표계
        
        # 컬럼 이름 통일 ('자치구_코드_명'으로 변경하여 고객님 데이터와 맞춤)
        # 공공 데이터에는 보통 'name'이 들어있음
        if 'name' in gdf.columns:
            gdf = gdf.rename(columns={'name': '자치구_코드_명'})
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf = gdf.rename(columns={'SIG_KOR_NM': '자치구_코드_명'})
            
        # 면적 계산 (도형 넓이 기반 근사값)
        gdf_area = gdf.to_crs(epsg=5179)
        gdf['면적(km²)'] = gdf_area.geometry.area / 1_000_000
        
    except Exception as e:
        st.error(f"지도를 인터넷에서 가져오는 중 오류 발생: {e}")
        return None

    # -----------------------------------------------------------
    # 사용자 데이터(CSV/Excel) 로드 및 병합
    # -----------------------------------------------------------
    
    # (A) 인구 데이터
    pop_file = './data/서울시 상권분석서비스(상주인구-자치구).csv'
    if os.path.exists(pop_file):
        try:
            df_pop = pd.read_csv(pop_file, encoding='cp949')
            # 자치구별 평균 상주인구
            df_pop_group = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
            
            # 지도에 합치기
            gdf = gdf.merge(df_pop_group, on='자치구_코드_명', how='left')
            gdf['인구_밀도(명/km²)'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
        except Exception as e:
            st.warning(f"인구 데이터 로드 오류: {e}")

    # (B) 상권(집객시설) 데이터
    biz_file = './data/서울시 상권분석서비스(집객시설-자치구).csv'
    if os.path.exists(biz_file):
        try:
            df_biz = pd.read_csv(biz_file, encoding='cp949')
            df_biz_group = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
            
            gdf = gdf.merge(df_biz_group, on='자치구_코드_명', how='left')
        except Exception as e:
            st.warning(f"상권 데이터 로드 오류: {e}")

    # (C) 교통(정류장) 데이터
    station_file = './data/GGD_StationInfo_M.xlsx'
    if os.path.exists(station_file):
        try:
            df_station = pd.read_excel(station_file)
            df_station = df_station.dropna(subset=['X', 'Y'])
            
            # 정류장 위치를 점으로 변환
            geometry = [Point(xy) for xy in zip(df_station['X'], df_station['Y'])]
            gdf_station = geopandas.GeoDataFrame(df_station, geometry=geometry, crs="EPSG:4326")
            
            # 공간 조인 (어느 구에 정류장이 있는지 확인)
            joined = geopandas.sjoin(gdf_station, gdf, how="inner", predicate="within")
            
            # 구별 개수 세기
            station_counts = joined.groupby('자치구_코드_명').size().reset_index(name='정류장_수')
            
            gdf = gdf.merge(station_counts, on='자치구_코드_명', how='left')
            gdf['정류장_밀도(개/km²)'] = gdf['정류장_수'] / gdf['면적(km²)']
            
            # (간단한 교통 부족 순위 계산)
            gdf['정류장_수'] = gdf['정류장_수'].fillna(0)
            gdf['교통_부족_순위'] = gdf['정류장_수'].rank(ascending=True, method='min') # 적을수록 1등(부족함)
            
        except Exception as e:
            st.warning(f"교통 데이터 분석 오류: {e}")

    return gdf

# --------------------------------------------------------------------------
# 3. 화면 표시
# --------------------------------------------------------------------------
gdf = load_and_merge_data()

if gdf is not None:
    # 데이터가 로드된 컬럼만 골라내기
    metrics = {
        '인구 밀도': '인구_밀도(명/km²)',
        '총 상주인구': '총_상주인구_수',
        '집객시설 수': '집객시설_수',
        '정류장 수': '정류장_수',
        '교통 부족 순위 (높을수록 좋음)': '교통_부족_순위'
    }
    # 실제 데이터프레임에 있는 컬럼만 필터링
    available_metrics = {k: v for k, v in metrics.items() if v in gdf.columns}

    # 사이드바 설정
    if available_metrics:
        with st.sidebar:
            st.header("📊 분석 옵션")
            selected_name = st.radio("보고 싶은 지표 선택", list(available_metrics.keys()))
            selected_col = available_metrics[selected_name]

        # 지도 시각화
        st.subheader(f"🗺️ 서울시 자치구별 {selected_name}")
        
        # 색상 설정 (순위는 숫자가 작을수록(1등) 빨갛게 표시하기 위해 색상 반전 등을 고려할 수 있음)
        colorscale = 'YlGnBu' 
        
        fig = px.choropleth_mapbox(
            gdf,
            geojson=gdf.geometry.__geo_interface__,
            locations=gdf.index,
            color=selected_col,
            mapbox_style="carto-positron",
            zoom=9.5,
            center={"lat": 37.5665, "lon": 126.9780},
            opacity=0.6,
            hover_name='자치구_코드_명',
            hover_data=list(available_metrics.values())
        )
        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=600)
        st.plotly_chart(fig, use_container_width=True)
        
        # 하단 통계 표
        st.subheader("📋 상세 데이터")
        display_cols = ['자치구_코드_명'] + list(available_metrics.values())
        st.dataframe(gdf[display_cols].sort_values(by=selected_col, ascending=False))
        
    else:
        st.info("지도 로드 성공! (아직 분석 데이터 파일이 업로드되지 않아 기본 지도만 표시됩니다.)")
        st.write("data 폴더에 csv/xlsx 파일을 올리면 자동으로 분석 내용이 추가됩니다.")
else:
    st.error("지도를 불러오지 못했습니다.")
