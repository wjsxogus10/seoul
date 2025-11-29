import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import plotly.graph_objects as go
import os
from shapely.geometry import Point

# --------------------------------------------------------------------------
# 1. 페이지 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")

# --------------------------------------------------------------------------
# 2. 데이터 로드 및 통합 함수
# --------------------------------------------------------------------------
@st.cache_data
def load_and_merge_data():
    # (A) 지도 데이터 (인터넷 공공 데이터 다운로드)
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326) # 지도 표시용 좌표계
        
        # 컬럼 이름 통일
        if 'name' in gdf.columns:
            gdf = gdf.rename(columns={'name': '자치구명'})
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf = gdf.rename(columns={'SIG_KOR_NM': '자치구명'})
            
        # 면적 계산 (도형 기반)
        gdf_area = gdf.to_crs(epsg=5179)
        gdf['면적(km²)'] = gdf_area.geometry.area / 1_000_000
    except Exception as e:
        st.error(f"지도 로드 실패: {e}")
        return None, None

    # (B) 데이터 병합 시작
    # -----------------------------------------------------------
    
    # 1. 상주 인구
    try:
        df_pop = pd.read_csv('./data/서울시 상권분석서비스(상주인구-자치구).csv', encoding='cp949')
        grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
        grp = grp.rename(columns={'자치구_코드_명': '자치구명'})
        gdf = gdf.merge(grp, on='자치구명', how='left')
        gdf['인구 밀도'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
    except: pass

    # 2. 집객시설 수
    try:
        df_biz = pd.read_csv('./data/서울시 상권분석서비스(집객시설-자치구).csv', encoding='cp949')
        grp = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
        grp = grp.rename(columns={'자치구_코드_명': '자치구명'})
        gdf = gdf.merge(grp, on='자치구명', how='left')
    except: pass

    # 3. 버스정류장 밀도 (좌표 계산)
    try:
        df_bus = pd.read_excel('./data/GGD_StationInfo_M.xlsx').dropna(subset=['X', 'Y'])
        geom = [Point(xy) for xy in zip(df_bus['X'], df_bus['Y'])]
        gdf_bus = geopandas.GeoDataFrame(df_bus, geometry=geom, crs="EPSG:4326")
        joined = geopandas.sjoin(gdf_bus, gdf, how="inner", predicate="within")
        cnt = joined.groupby('자치구명').size().reset_index(name='버스정류장_수')
        gdf = gdf.merge(cnt, on='자치구명', how='left')
        gdf['버스정류장_수'] = gdf['버스정류장_수'].fillna(0)
        gdf['버스정류장 밀도'] = gdf['버스정류장_수'] / gdf['면적(km²)']
    except: 
        gdf['버스정류장 밀도'] = 0

    # 4. 지하철 밀도 (업로드한 밀도 파일 사용)
    density_file = './data/지하철 밀도.xlsx - Sheet1.csv'
    if os.path.exists(density_file):
        try:
            try: df_dens = pd.read_csv(density_file, encoding='utf-8')
            except: df_dens = pd.read_csv(density_file, encoding='cp949')
            
            # 컬럼 매핑 ('자치구_코드_명', '지하철역_밀도(개/km²)')
            gu_col = next((c for c in df_dens.columns if '자치구' in c), None)
            dens_col = next((c for c in df_dens.columns if '밀도' in c), None)
            
            if gu_col and dens_col:
                df_dens = df_dens.rename(columns={gu_col: '자치구명', dens_col: '지하철역 밀도'})
                gdf = gdf.merge(df_dens[['자치구명', '지하철역 밀도']], on='자치구명', how='left')
                gdf['지하철역 밀도'] = gdf['지하철역 밀도'].fillna(0)
            else:
                gdf['지하철역 밀도'] = 0
        except: gdf['지하철역 밀도'] = 0
    else:
        gdf['지하철역 밀도'] = 0

    # 5. 지하철 위치 좌표 (점 찍기용)
    coord_file = './data/지하철 위경도.xlsx - 시트1.csv'
    df_stations = pd.DataFrame()
    if os.path.exists(coord_file):
        try:
            try: df_stations = pd.read_csv(coord_file, encoding='utf-8')
            except: df_stations = pd.read_csv(coord_file, encoding='cp949')
            # point_x, point_y가 있어야 함
            if 'point_x' not in df_stations.columns:
                df_stations = pd.DataFrame()
        except: pass

    # 6. 교통 부족 순위 (버스 + 지하철 합계가 낮을수록 1등)
    if '버스정류장 밀도' in gdf.columns and '지하철역 밀도' in gdf.columns:
        total = gdf['버스정류장 밀도'] + gdf['지하철역 밀도']
        gdf['교통 부족 순위'] = total.rank(ascending=True, method='min')

    return gdf, df_stations

# --------------------------------------------------------------------------
# 3. 화면 구성 및 시각화
# --------------------------------------------------------------------------
result = load_and_merge_data()

if result is None or result[0] is None:
    st.error("데이터 로드 중 문제가 발생했습니다.")
    st.stop()

gdf, df_stations = result

st.sidebar.header("🔍 분석 옵션")

# [요청하신 순서 적용]
metrics_order = [
    ('상주 인구', '총_상주인구_수'),
    ('인구 밀도', '인구 밀도'),
    ('집객시설 수', '집객시설_수'),
    ('버스정류장 밀도', '버스정류장 밀도'),
    ('지하철역 밀도', '지하철역 밀도'),
    ('교통 부족 순위', '교통 부족 순위')
]

# 데이터가 존재하는 지표만 메뉴에 표시
valid_metrics = {}
for k, v in metrics_order:
    if v in gdf.columns:
        if gdf[v].sum() > 0 or k == '교통 부족 순위':
            valid_metrics[k] = v

if valid_metrics:
    # 1. 지표 선택
    selected_name = st.sidebar.radio("분석할 지표 선택", list(valid_metrics.keys()))
    selected_col = valid_metrics[selected_name]
    
    st.sidebar.markdown("---")
    # 2. 개수 조절 슬라이더
    display_count = st.sidebar.slider("📊 그래프/표 표시 개수", 5, 25, 10)
    st.sidebar.markdown("---")
    # 3. 자치구 선택
    district_list = ['전체 서울시'] + sorted(gdf['자치구명'].unique().tolist())
    selected_district = st.sidebar.selectbox("자치구 상세 보기", district_list)

    # --- (1) 지도 시각화 ---
    st.subheader(f"🗺️ 서울시 {selected_name} 지도")
    
    center_lat, center_lon, zoom = 37.5665, 126.9780, 9.5
    if selected_district != '전체 서울시':
        d = gdf[gdf['자치구명'] == selected_district]
        center_lat, center_lon = d.geometry.centroid.y.values[0], d.geometry.centroid.x.values[0]
        zoom = 11.5

    # 교통 부족 순위는 1위(낮은 값)가 빨간색이어야 함 -> Reds_r (역순)
    # 나머지는 값이 높을수록 진한 색 -> YlGnBu
    colorscale = 'Reds_r' if '부족' in selected_name else 'YlGnBu'

    fig = px.choropleth_mapbox(
        gdf, geojson=gdf.geometry.__geo_interface__, locations=gdf.index,
        color=selected_col, mapbox_style="carto-positron", zoom=zoom,
        center={"lat": center_lat, "lon": center_lon}, opacity=0.6,
        hover_name='자치구명', hover_data=[selected_col], color_continuous_scale=colorscale
    )
    
    # [특수 기능] '지하철역 밀도' 선택 시 실제 역사 위치(점) 표시
    if '지하철' in selected_name and not df_stations.empty:
        fig.add_trace(go.Scattermapbox(
            lat=df_stations['point_y'], lon=df_stations['point_x'],
            mode='markers', marker=go.scattermapbox.Marker(size=5, color='red'),
            name='지하철역 위치',
            text=df_stations['name'] if 'name' in df_stations.columns else None
        ))

    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
    st.plotly_chart(fig, use_container_width=True)

    # --- (2) 그래프 시각화 ---
    st.subheader(f"📊 {selected_name} 순위 비교")
    col1, col2 = st.columns([3, 1])
    with col2:
        sort_opt = st.radio("정렬:", ["상위", "하위"], horizontal=True)
    
    # 정렬 및 개수 자르기
    if sort_opt == "상위":
        df_sorted = gdf.sort_values(by=selected_col, ascending=False).head(display_count)
    else:
        df_sorted = gdf.sort_values(by=selected_col, ascending=True).head(display_count)
        
    # 선택된 자치구 강조 (빨간색)
    df_sorted['color'] = df_sorted['자치구명'].apply(lambda x: '#FF4B4B' if x == selected_district else '#8884d8')
    
    fig_bar = px.bar(
        df_sorted, x='자치구명', y=selected_col, 
        text=selected_col, color='color', color_discrete_map='identity'
    )
    
    # 숫자 포맷 (순위/인구는 정수, 밀도는 소수점)
    fmt = '%{text:.0f}' if '순위' in selected_name or '인구' in selected_name else '%{text:.4f}'
    fig_bar.update_traces(texttemplate=fmt, textposition='outside')
    fig_bar.update_layout(showlegend=False, xaxis_title=None)
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- (3) 상세 표 ---
    st.markdown("---")
    st.subheader("📋 상세 데이터 표")
    cols_to_show = ['자치구명'] + list(valid_metrics.values())
    
    # 표도 정렬 옵션에 맞춰서 보여줌
    df_table = gdf[cols_to_show].sort_values(by=selected_col, ascending=(sort_opt=="하위")).head(display_count)
    st.dataframe(df_table, use_container_width=True, hide_index=True)
    
    # 전체 데이터 다운로드 버튼
    csv = gdf[cols_to_show].to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 전체 데이터 다운로드 (CSV)", csv, "seoul_analysis.csv", "text/csv")

else:
    st.warning("분석할 데이터 파일이 없습니다. data 폴더를 확인해주세요.")
