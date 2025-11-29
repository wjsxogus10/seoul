import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import plotly.graph_objects as go
import os

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
        col_map = {'name': '자치구명', 'SIG_KOR_NM': '자치구명'}
        gdf = gdf.rename(columns=col_map)
        
        gdf_area = gdf.to_crs(epsg=5179)
        gdf['면적(km²)'] = gdf_area.geometry.area / 1_000_000
    except Exception as e:
        st.error(f"지도 로드 실패: {e}")
        return None, None

    # -----------------------------------------------------------
    # (B) 사용자 데이터 병합
    # -----------------------------------------------------------
    
    # 1. [핵심] 지하철 밀도 (업로드하신 파일 적용)
    # 파일명: 지하철 밀도.xlsx - Sheet1.csv
    density_file = '지하철 밀도.xlsx - Sheet1.csv'
    density_path = f'./data/{density_file}'
    
    if os.path.exists(density_path):
        try:
            try: df_dens = pd.read_csv(density_path, encoding='utf-8')
            except: df_dens = pd.read_csv(density_path, encoding='cp949')
            
            # 컬럼 매핑: '자치구_코드_명' -> '자치구명', '지하철역_밀도(개/km²)' -> '지하철역 밀도'
            # 파일에 있는 정확한 컬럼명을 찾아서 바꿈
            cols = df_dens.columns
            gu_col = next((c for c in cols if '자치구' in c), None)
            dens_col = next((c for c in cols if '밀도' in c), None)
            cnt_col = next((c for c in cols if '지하철역_수' in c or '역_수' in c), None)

            if gu_col and dens_col:
                rename_dict = {gu_col: '자치구명', dens_col: '지하철역 밀도'}
                if cnt_col:
                    rename_dict[cnt_col] = '지하철역_수'
                
                df_dens = df_dens.rename(columns=rename_dict)
                
                # 병합
                merge_cols = ['자치구명', '지하철역 밀도']
                if '지하철역_수' in df_dens.columns:
                    merge_cols.append('지하철역_수')
                    
                gdf = gdf.merge(df_dens[merge_cols], on='자치구명', how='left')
                
                # 결측치 처리
                gdf['지하철역 밀도'] = gdf['지하철역 밀도'].fillna(0)
                if '지하철역_수' in gdf.columns:
                    gdf['지하철역_수'] = gdf['지하철역_수'].fillna(0)
                else:
                    gdf['지하철역_수'] = 0
                    
                st.sidebar.success("✅ 지하철 밀도 데이터 로드 성공!")
            else:
                st.sidebar.error("❌ 지하철 파일 컬럼 인식 실패")
                gdf['지하철역 밀도'] = 0
                gdf['지하철역_수'] = 0
        except: 
            gdf['지하철역 밀도'] = 0
            gdf['지하철역_수'] = 0
    else:
        # 파일이 없으면 0
        gdf['지하철역 밀도'] = 0
        gdf['지하철역_수'] = 0

    # 2. [선택] 지하철 위치 좌표 (점 찍기용 - 파일 있으면 사용)
    coord_file = '지하철 위경도.xlsx - 시트1.csv'
    coord_path = f'./data/{coord_file}'
    df_stations = pd.DataFrame()
    if os.path.exists(coord_path):
        try:
            try: df_stations = pd.read_csv(coord_path, encoding='utf-8')
            except: df_stations = pd.read_csv(coord_path, encoding='cp949')
            # point_x, point_y 확인
            if 'point_x' not in df_stations.columns:
                df_stations = pd.DataFrame()
        except: pass

    # 3. 상주 인구
    try:
        df_pop = pd.read_csv('./data/서울시 상권분석서비스(상주인구-자치구).csv', encoding='cp949')
        grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index().rename(columns={'자치구_코드_명':'자치구명'})
        gdf = gdf.merge(grp, on='자치구명', how='left')
        gdf['인구 밀도'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
    except: pass

    # 4. 집객시설 수
    try:
        df_biz = pd.read_csv('./data/서울시 상권분석서비스(집객시설-자치구).csv', encoding='cp949')
        grp = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index().rename(columns={'자치구_코드_명':'자치구명'})
        gdf = gdf.merge(grp, on='자치구명', how='left')
    except: pass

    # 5. 버스정류장 밀도
    try:
        from shapely.geometry import Point
        df_bus = pd.read_excel('./data/GGD_StationInfo_M.xlsx').dropna(subset=['X','Y'])
        geom = [Point(xy) for xy in zip(df_bus['X'], df_bus['Y'])]
        gdf_bus = geopandas.GeoDataFrame(df_bus, geometry=geom, crs="EPSG:4326")
        joined = geopandas.sjoin(gdf_bus, gdf, how="inner", predicate="within")
        cnt = joined.groupby('자치구명').size().reset_index(name='버스_cnt')
        gdf = gdf.merge(cnt, on='자치구명', how='left')
        gdf['버스정류장 밀도'] = gdf['버스_cnt'].fillna(0) / gdf['면적(km²)']
    except: 
        gdf['버스정류장 밀도'] = 0

    # 6. 교통 부족 순위
    # 버스나 지하철 중 하나라도 있으면 계산
    bus_dens = gdf['버스정류장 밀도'] if '버스정류장 밀도' in gdf.columns else 0
    sub_dens = gdf['지하철역 밀도'] if '지하철역 밀도' in gdf.columns else 0
    
    total_density = bus_dens + sub_dens
    # 밀도가 낮을수록(부족할수록) 1등
    gdf['교통 부족 순위'] = total_density.rank(ascending=True, method='min')

    return gdf, df_stations

# --------------------------------------------------------------------------
# 3. 화면 구성
# --------------------------------------------------------------------------
result = load_and_merge_data()
if result is None or result[0] is None:
    st.stop()

gdf, df_stations = result

st.sidebar.header("🔍 분석 옵션")

# [요청하신 순서]
metrics_order = [
    ('상주 인구', '총_상주인구_수'),
    ('인구 밀도', '인구 밀도'),
    ('집객시설 수', '집객시설_수'),
    ('버스정류장 밀도', '버스정류장 밀도'),
    ('지하철역 밀도', '지하철역 밀도'),
    ('교통 부족 순위', '교통 부족 순위')
]

# 데이터가 있는 지표만 필터링 (값이 하나라도 있으면 표시)
valid_metrics = {}
for k, v in metrics_order:
    if v in gdf.columns:
        # 데이터가 있거나(sum > 0), 부족 순위인 경우
        if gdf[v].sum() > 0 or k == '교통 부족 순위':
            valid_metrics[k] = v

if valid_metrics:
    selected_name = st.sidebar.radio("분석할 지표 선택", list(valid_metrics.keys()))
    selected_col = valid_metrics[selected_name]
    
    st.sidebar.markdown("---")
    display_count = st.sidebar.slider("📊 그래프/표 표시 개수", 5, 25, 10)
    st.sidebar.markdown("---")

    district_list = ['전체 서울시'] + sorted(gdf['자치구명'].unique().tolist())
    selected_district = st.sidebar.selectbox("자치구 상세 보기", district_list)

    # (1) 지도
    st.subheader(f"🗺️ 서울시 {selected_name} 지도")
    
    center_lat, center_lon, zoom = 37.5665, 126.9780, 9.5
    if selected_district != '전체 서울시':
        d = gdf[gdf['자치구명'] == selected_district]
        center_lat, center_lon = d.geometry.centroid.y.values[0], d.geometry.centroid.x.values[0]
        zoom = 11.5

    colorscale = 'Reds_r' if '부족' in selected_name else 'YlGnBu'

    fig = px.choropleth_mapbox(
        gdf, geojson=gdf.geometry.__geo_interface__, locations=gdf.index,
        color=selected_col, mapbox_style="carto-positron", zoom=zoom,
        center={"lat": center_lat, "lon": center_lon}, opacity=0.6,
        hover_name='자치구명', hover_data=[selected_col], color_continuous_scale=colorscale
    )
    
    # [Point] 지하철 역 위치 점 찍기 (좌표 파일이 있을 때만)
    if '지하철' in selected_name and not df_stations.empty:
        fig.add_trace(go.Scattermapbox(
            lat=df_stations['point_y'], lon=df_stations['point_x'],
            mode='markers', marker=go.scattermapbox.Marker(size=5, color='red'),
            name='역 위치'
        ))
        
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
    st.plotly_chart(fig, use_container_width=True)

    # (2) 그래프
    st.subheader(f"📊 {selected_name} 순위")
    col1, col2 = st.columns([3, 1])
    with col2:
        sort_opt = st.radio("정렬:", ["상위", "하위"], horizontal=True)
    
    if sort_opt == "상위":
        df_sorted = gdf.sort_values(by=selected_col, ascending=False).head(display_count)
    else:
        df_sorted = gdf.sort_values(by=selected_col, ascending=True).head(display_count)
        
    df_sorted['color'] = df_sorted['자치구명'].apply(lambda x: '#FF4B4B' if x == selected_district else '#8884d8')
    
    fig_bar = px.bar(
        df_sorted, x='자치구명', y=selected_col, 
        text=selected_col, color='color', color_discrete_map='identity'
    )
    
    fmt = '%{text:.0f}' if '순위' in selected_name or '인구' in selected_name else '%{text:.4f}'
    fig_bar.update_traces(texttemplate=fmt, textposition='outside')
    fig_bar.update_layout(showlegend=False, xaxis_title=None)
    st.plotly_chart(fig_bar, use_container_width=True)

    # (3) 표
    st.markdown("---")
    st.subheader("📋 상세 데이터 표")
    cols_to_show = ['자치구명'] + list(valid_metrics.values())
    st.dataframe(
        gdf[cols_to_show].sort_values(by=selected_col, ascending=(sort_opt=="하위")).head(display_count),
        use_container_width=True, hide_index=True
    )
    
    csv = gdf[cols_to_show].to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 데이터 다운로드", csv, "seoul_analysis.csv", "text/csv")

else:
    st.warning("데이터가 로드되지 않았습니다. data 폴더에 파일을 확인해주세요.")
