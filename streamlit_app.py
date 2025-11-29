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
# 2. 데이터 로드 및 병합
# --------------------------------------------------------------------------
@st.cache_data
def load_and_merge_data():
    # -----------------------------------------------------------
    # (A) 지도 데이터 (인터넷 공공 데이터)
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
    # (B) 사용자 데이터 병합
    # -----------------------------------------------------------
    
    # 1. 인구 데이터
    pop_file = './data/서울시 상권분석서비스(상주인구-자치구).csv'
    if os.path.exists(pop_file):
        try:
            df_pop = pd.read_csv(pop_file, encoding='cp949')
            df_grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
            df_grp.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
            gdf = gdf.merge(df_grp, on='자치구명', how='left')
            gdf['인구_밀도(명/km²)'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
        except: pass

    # 2. 상권 데이터
    biz_file = './data/서울시 상권분석서비스(집객시설-자치구).csv'
    if os.path.exists(biz_file):
        try:
            df_biz = pd.read_csv(biz_file, encoding='cp949')
            df_grp = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
            df_grp.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
            gdf = gdf.merge(df_grp, on='자치구명', how='left')
        except: pass

    # 3. 버스 정류장 데이터
    bus_file = './data/GGD_StationInfo_M.xlsx'
    if os.path.exists(bus_file):
        try:
            df = pd.read_excel(bus_file)
            df = df.dropna(subset=['X', 'Y'])
            geom = [Point(xy) for xy in zip(df['X'], df['Y'])]
            gdf_bus = geopandas.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")
            joined = geopandas.sjoin(gdf_bus, gdf, how="inner", predicate="within")
            cnt = joined.groupby('자치구명').size().reset_index(name='버스정류장_수')
            gdf = gdf.merge(cnt, on='자치구명', how='left')
            gdf['버스정류장_수'] = gdf['버스정류장_수'].fillna(0)
            gdf['버스정류장_밀도(개/km²)'] = gdf['버스정류장_수'] / gdf['면적(km²)']
        except: pass

    # -----------------------------------------------------------
    # (C) [수정됨] 지하철 데이터 (업로드한 파일명 정확히 지정)
    # -----------------------------------------------------------
    # 파일명이 '지하철'이 들어간 csv를 찾거나, 특정 파일명을 지정
    subway_file_name = '지하철 위경도.xlsx - 시트1.csv'
    subway_path = f'./data/{subway_file_name}'
    
    # 만약 정확한 이름이 없으면 폴더 내 검색
    if not os.path.exists(subway_path):
        candidates = [f for f in os.listdir('./data') if '지하철' in f and f.endswith('.csv')]
        if candidates:
            subway_path = f'./data/{candidates[0]}'

    if os.path.exists(subway_path):
        try:
            # 인코딩 시도 (utf-8 아니면 cp949)
            try:
                df_sub = pd.read_csv(subway_path, encoding='utf-8')
            except:
                df_sub = pd.read_csv(subway_path, encoding='cp949')
            
            # 컬럼명 찾기 ('위도', '경도'가 포함된 컬럼 자동 찾기)
            lat_col = next((c for c in df_sub.columns if '위도' in c or 'lat' in c.lower()), None)
            lon_col = next((c for c in df_sub.columns if '경도' in c or 'lon' in c.lower()), None)

            if lat_col and lon_col:
                df_sub = df_sub.dropna(subset=[lat_col, lon_col])
                geom = [Point(xy) for xy in zip(df_sub[lon_col], df_sub[lat_col])]
                gdf_sub = geopandas.GeoDataFrame(df_sub, geometry=geom, crs="EPSG:4326")
                
                joined = geopandas.sjoin(gdf_sub, gdf, how="inner", predicate="within")
                cnt = joined.groupby('자치구명').size().reset_index(name='지하철역_수')
                
                gdf = gdf.merge(cnt, on='자치구명', how='left')
                gdf['지하철역_수'] = gdf['지하철역_수'].fillna(0)
                gdf['지하철역_밀도(개/km²)'] = gdf['지하철역_수'] / gdf['면적(km²)']
                
            else:
                st.warning(f"지하철 파일에서 '위도', '경도' 컬럼을 찾을 수 없습니다. (발견된 컬럼: {list(df_sub.columns)})")
                gdf['지하철역_수'] = 0
                gdf['지하철역_밀도(개/km²)'] = 0

        except Exception as e:
            st.warning(f"지하철 데이터 로드 중 오류: {e}")
            gdf['지하철역_수'] = 0
            gdf['지하철역_밀도(개/km²)'] = 0
    else:
        # 파일이 없을 때
        gdf['지하철역_수'] = 0
        gdf['지하철역_밀도(개/km²)'] = 0
    
    # 교통 부족 순위 계산 (버스 + 지하철)
    if '버스정류장_수' in gdf.columns and '지하철역_수' in gdf.columns:
        gdf['교통_부족_순위'] = (gdf['버스정류장_수'] + gdf['지하철역_수']).rank(ascending=True, method='min')

    return gdf

# --------------------------------------------------------------------------
# 3. 화면 구성
# --------------------------------------------------------------------------
gdf = load_and_merge_data()

if gdf is not None:
    st.sidebar.header("🔍 분석 옵션")
    
    metrics = {
        '지하철역 밀도': '지하철역_밀도(개/km²)', # <-- 1순위로 배치
        '인구 밀도': '인구_밀도(명/km²)',
        '버스정류장 밀도': '버스정류장_밀도(개/km²)',
        '교통 부족 순위': '교통_부족_순위',
        '총 상주인구': '총_상주인구_수',
        '집객시설 수': '집객시설_수'
    }
    
    valid_metrics = {k: v for k, v in metrics.items() if v in gdf.columns}
    
    if valid_metrics:
        selected_name = st.sidebar.radio("분석할 지표", list(valid_metrics.keys()))
        selected_col = valid_metrics[selected_name]
        
        district_list = ['전체 서울시'] + sorted(gdf['자치구명'].unique().tolist())
        selected_district = st.sidebar.selectbox("자치구 상세", district_list)

        # (1) 지도
        st.subheader(f"🗺️ 서울시 {selected_name} 지도")
        
        center_lat, center_lon, zoom = 37.5665, 126.9780, 9.5
        if selected_district != '전체 서울시':
            d = gdf[gdf['자치구명'] == selected_district]
            center_lat, center_lon = d.geometry.centroid.y.values[0], d.geometry.centroid.x.values[0]
            zoom = 11.5

        fig = px.choropleth_mapbox(
            gdf, geojson=gdf.geometry.__geo_interface__, locations=gdf.index,
            color=selected_col, mapbox_style="carto-positron", zoom=zoom,
            center={"lat": center_lat, "lon": center_lon}, opacity=0.6,
            hover_name='자치구명', hover_data=[selected_col], color_continuous_scale='YlGnBu'
        )
        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
        st.plotly_chart(fig, use_container_width=True)

        # (2) 그래프
        st.subheader(f"📊 {selected_name} 순위")
        sort_opt = st.radio("정렬:", ["상위 10개", "하위 10개", "전체"], horizontal=True)
        df_sorted = gdf.sort_values(by=selected_col, ascending=False)
        
        if sort_opt == "상위 10개": data = df_sorted.head(10)
        elif sort_opt == "하위 10개": data = df_sorted.tail(10).sort_values(by=selected_col)
        else: data = df_sorted
        
        data['color'] = data['자치구명'].apply(lambda x: 'red' if x == selected_district else 'blue')
        fig_bar = px.bar(data, x='자치구명', y=selected_col, color='color', color_
