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
    # (A) 지도 데이터
    # -----------------------------------------------------------
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326)
        col_map = {'name': '자치구명', 'SIG_KOR_NM': '자치구명'}
        gdf = gdf.rename(columns=col_map)
        gdf_area = gdf.to_crs(epsg=5179)
        gdf['면적(km²)'] = gdf_area.geometry.area / 1_000_000
    except:
        return None

    # -----------------------------------------------------------
    # (B) 사용자 데이터 병합
    # -----------------------------------------------------------
    
    # 1. 인구
    try:
        df_pop = pd.read_csv('./data/서울시 상권분석서비스(상주인구-자치구).csv', encoding='cp949')
        df_grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
        df_grp.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
        gdf = gdf.merge(df_grp, on='자치구명', how='left')
        gdf['인구_밀도(명/km²)'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
    except: pass

    # 2. 상권
    try:
        df_biz = pd.read_csv('./data/서울시 상권분석서비스(집객시설-자치구).csv', encoding='cp949')
        df_grp = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
        df_grp.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
        gdf = gdf.merge(df_grp, on='자치구명', how='left')
    except: pass

    # 3. 버스
    try:
        df = pd.read_excel('./data/GGD_StationInfo_M.xlsx')
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
    # (C) [강력 수정] 지하철 데이터 디버깅 로직
    # -----------------------------------------------------------
    subway_path = None
    # 1. 사용자가 올린 정확한 파일명 찾기
    specific_file = '지하철 위경도.xlsx - 시트1.csv'
    if os.path.exists(f'./data/{specific_file}'):
        subway_path = f'./data/{specific_file}'
    else:
        # 2. 없으면 폴더 내 csv 중 '지하철' 들어간 거 아무거나 잡기
        candidates = [f for f in os.listdir('./data') if f.endswith('.csv') and ('지하철' in f or 'subway' in f)]
        if candidates:
            subway_path = f'./data/{candidates[0]}'

    if subway_path:
        try:
            # 인코딩 자동 감지 시도
            try:
                df_sub = pd.read_csv(subway_path, encoding='utf-8')
            except:
                df_sub = pd.read_csv(subway_path, encoding='cp949')

            # --- [디버깅] 컬럼 확인용 ---
            st.sidebar.markdown("---")
            st.sidebar.warning(f"📂 읽은 지하철 파일: {os.path.basename(subway_path)}")
            st.sidebar.write("파일 안의 컬럼들:", df_sub.columns.tolist())

            # 컬럼명 정리 (공백 제거, 소문자 변환 없이 원본 비교하되, 유연하게 찾기)
            # 위도 찾기
            lat_col = next((c for c in df_sub.columns if any(k in c for k in ['위도', 'lat', 'Lat', 'Y', 'y'])), None)
            # 경도 찾기
            lon_col = next((c for c in df_sub.columns if any(k in c for k in ['경도', 'lon', 'Lon', 'X', 'x'])), None)

            if lat_col and lon_col:
                st.sidebar.success(f"✅ 좌표 컬럼 찾음: {lat_col}, {lon_col}")
                
                df_sub = df_sub.dropna(subset=[lat_col, lon_col])
                # 좌표가 문자로 되어있을 경우 숫자로 변환
                df_sub[lat_col] = pd.to_numeric(df_sub[lat_col], errors='coerce')
                df_sub[lon_col] = pd.to_numeric(df_sub[lon_col], errors='coerce')
                df_sub = df_sub.dropna(subset=[lat_col, lon_col])

                geom = [Point(xy) for xy in zip(df_sub[lon_col], df_sub[lat_col])]
                gdf_sub = geopandas.GeoDataFrame(df_sub, geometry=geom, crs="EPSG:4326")
                
                joined = geopandas.sjoin(gdf_sub, gdf, how="inner", predicate="within")
                cnt = joined.groupby('자치구명').size().reset_index(name='지하철역_수')
                
                gdf = gdf.merge(cnt, on='자치구명', how='left')
                gdf['지하철역_수'] = gdf['지하철역_수'].fillna(0)
                gdf['지하철역_밀도(개/km²)'] = gdf['지하철역_수'] / gdf['면적(km²)']
            else:
                st.sidebar.error("❌ '위도/경도' 컬럼을 못 찾았습니다.")
        except Exception as e:
            st.sidebar.error(f"지하철 파일 읽기 에러: {e}")
            gdf['지하철역_수'] = 0
            gdf['지하철역_밀도(개/km²)'] = 0
    else:
        st.sidebar.error("❌ 지하철 데이터 파일(.csv)이 data 폴더에 없습니다.")
        gdf['지하철역_수'] = 0
        gdf['지하철역_밀도(개/km²)'] = 0

    # 교통 부족 순위 업데이트
    if '버스정류장_수' in gdf.columns:
        sub_cnt = gdf['지하철역_수'] if '지하철역_수' in gdf.columns else 0
        gdf['교통_부족_순위'] = (gdf['버스정류장_수'] + sub_cnt).rank(ascending=True, method='min')

    return gdf

# --------------------------------------------------------------------------
# 3. 화면 표시
# --------------------------------------------------------------------------
gdf = load_and_merge_data()

if gdf is not None:
    st.sidebar.header("🔍 분석 옵션")
    
    metrics = {
        '지하철역 밀도': '지하철역_밀도(개/km²)',
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

        # 지도
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
        st.plotly_chart(fig, use_container_width=True)

        # 그래프
        st.subheader(f"📊 {selected_name} 순위")
        df_sorted = gdf.sort_values(by=selected_col, ascending=False)
        fig_bar = px.bar(df_sorted, x='자치구명', y=selected_col)
        st.plotly_chart(fig_bar, use_container_width=True)
        
        # 표
        st.dataframe(gdf[['자치구명'] + list(valid_metrics.values())].sort_values(by=selected_col, ascending=False))
