streamlit
pandas
geopandas
plotly
openpyxl
shapely
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
# 2. 데이터 로드 및 병합 함수 (안정성 강화 버전)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="데이터를 불러오는 중입니다...")
def load_and_merge_data():
    # (A) 지도 데이터 (GeoJSON) - 실패하면 앱 실행 불가
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326)
        
        # 컬럼 이름 통일 ('name' -> '자치구명')
        if 'name' in gdf.columns:
            gdf['자치구명'] = gdf['name']
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf['자치구명'] = gdf['SIG_KOR_NM']
        else:
            st.error("❌ 지도 데이터에 '자치구 이름'이 없습니다.")
            return None, None
            
        gdf['면적(km²)'] = gdf.geometry.to_crs(epsg=5179).area / 1_000_000
    except Exception as e:
        st.error(f"❌ 지도 로드 실패: {e}")
        return None, None

    # (B) 사용자 데이터 병합
    # 1. 컬럼 초기화 (파일이 없어도 에러 안 나게 0으로 채움)
    init_cols = ['총_상주인구_수', '인구 밀도', '집객시설 수', '버스정류장_수', '버스정류장 밀도', '지하철역_수', '지하철역 밀도']
    for c in init_cols:
        gdf[c] = 0

    # 2. 상주 인구 로드
    try:
        df_pop = pd.read_csv('./data/서울시 상권분석서비스(상주인구-자치구).csv', encoding='cp949')
        grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index().rename(columns={'자치구_코드_명':'자치구명'})
        gdf = gdf.merge(grp, on='자치구명', how='left', suffixes=('', '_new'))
        if '총_상주인구_수_new' in gdf.columns:
            gdf['총_상주인구_수'] = gdf['총_상주인구_수_new'].fillna(0)
        gdf['인구 밀도'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
    except: pass

    # 3. 집객시설 로드
    try:
        df_biz = pd.read_csv('./data/서울시 상권분석서비스(집객시설-자치구).csv', encoding='cp949')
        grp = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index().rename(columns={'자치구_코드_명':'자치구명'})
        gdf = gdf.merge(grp, on='자치구명', how='left', suffixes=('', '_new'))
        if '집객시설_수_new' in gdf.columns:
            gdf['집객시설 수'] = gdf['집객시설_수_new'].fillna(0)
    except: pass

    # 4. 버스 정류장 로드 (좌표 5181 -> 4326 변환)
    try:
        df_bus = pd.read_excel('./data/GGD_StationInfo_M.xlsx').dropna(subset=['X', 'Y'])
        geom = [Point(xy) for xy in zip(df_bus['X'], df_bus['Y'])]
        # 버스 좌표계가 5181이라고 가정 (서울/경기 공공데이터 표준)
        gdf_bus = geopandas.GeoDataFrame(df_bus, geometry=geom, crs="EPSG:5181").to_crs(epsg=4326)
        
        joined = geopandas.sjoin(gdf_bus, gdf[['자치구명', 'geometry']], how="inner", predicate="within")
        cnt = joined.groupby('자치구명').size().reset_index(name='버스_cnt')
        
        gdf = gdf.merge(cnt, on='자치구명', how='left')
        if '버스_cnt' in gdf.columns:
            gdf['버스정류장_수'] = gdf['버스_cnt'].fillna(0)
        gdf['버스정류장 밀도'] = gdf['버스정류장_수'] / gdf['면적(km²)']
    except: pass

    # 5. 지하철 밀도 (업로드한 파일 사용)
    # 파일명: 지하철 밀도.CSV
    density_path = './data/지하철 밀도.CSV'
    if os.path.exists(density_path):
        try:
            try: df_dens = pd.read_csv(density_path, encoding='utf-8')
            except: df_dens = pd.read_csv(density_path, encoding='cp949')
            
            # 컬럼 찾기
            gu_col = next((c for c in df_dens.columns if '자치구' in c), None)
            dens_col = next((c for c in df_dens.columns if '밀도' in c), None)
            cnt_col = next((c for c in df_dens.columns if '역' in c and '수' in c), None)
            
            if gu_col and dens_col:
                rename_map = {gu_col: '자치구명', dens_col: '지하철역 밀도'}
                if cnt_col: rename_map[cnt_col] = '지하철역_수'
                
                df_dens = df_dens.rename(columns=rename_map)
                
                # 병합
                cols_to_merge = ['자치구명', '지하철역 밀도']
                if '지하철역_수' in df_dens.columns: cols_to_merge.append('지하철역_수')
                
                gdf = gdf.merge(df_dens[cols_to_merge], on='자치구명', how='left', suffixes=('', '_sub'))
                if '지하철역 밀도_sub' in gdf.columns:
                    gdf['지하철역 밀도'] = gdf['지하철역 밀도_sub'].fillna(0)
                if '지하철역_수_sub' in gdf.columns:
                    gdf['지하철역_수'] = gdf['지하철역_수_sub'].fillna(0)
        except: pass

    # 6. 지하철 좌표 (점 찍기용)
    coord_path = './data/지하철 위경도.CSV'
    df_stations = pd.DataFrame()
    if os.path.exists(coord_path):
        try:
            try: df_stations = pd.read_csv(coord_path, encoding='utf-8')
            except: df_stations = pd.read_csv(coord_path, encoding='cp949')
        except: pass

    # 7. 대중교통 밀도 & 교통 부족 순위 계산
    gdf['총_교통수단_수'] = gdf['버스정류장_수'] + gdf['지하철역_수']
    gdf['대중교통 밀도'] = gdf['총_교통수단_수'] / gdf['면적(km²)']
    
    # 인구 대비 교통수단 비율 (인구가 0이면 1로 나누어 에러 방지)
    pop_safe = gdf['총_상주인구_수'].replace(0, 1)
    gdf['인구 대비 교통수단 비율'] = gdf['총_교통수단_수'] / pop_safe
    
    # 부족 순위 (비율이 낮을수록 1등)
    gdf['교통 부족 순위'] = gdf['인구 대비 교통수단 비율'].rank(ascending=True, method='min')

    return gdf, df_stations

# --------------------------------------------------------------------------
# 3. 화면 시각화 로직
# --------------------------------------------------------------------------
result = load_and_merge_data()

if result is None or result[0] is None:
    st.error("데이터 로드 중 오류가 발생했습니다.")
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
    ('대중교통 밀도 (버스+지하철)', '대중교통 밀도'),
    ('교통 부족 순위 (인구 대비)', '교통 부족 순위')
]

# 데이터가 있는 항목만 필터링
valid_metrics = {}
for k, v in metrics_order:
    if v in gdf.columns:
        valid_metrics[k] = v

if valid_metrics:
    # 1. 지표 선택
    selected_name = st.sidebar.radio("분석할 지표 선택", list(valid_metrics.keys()))
    selected_col = valid_metrics[selected_name]
    
    st.sidebar.markdown("---")
    # 2. 개수 조절
    display_count = st.sidebar.slider("📊 그래프/표 표시 개수", 5, 25, 10)
    st.sidebar.markdown("---")
    # 3. 자치구 선택
    district_list = ['전체 서울시'] + sorted(gdf['자치구명'].unique().tolist())
    selected_district = st.sidebar.selectbox("자치구 상세 보기", district_list)

    # --- 색상 설정 (인구=파랑, 교통/순위=빨강) ---
    if selected_col in ['총_상주인구_수', '인구 밀도', '집객시설 수']:
        colorscale = 'Blues'
    else:
        colorscale = 'Reds'

    # ==========================================
    # [레이아웃] 지도(왼쪽) | 그래프(오른쪽)
    # ==========================================
    col_map, col_chart = st.columns([1, 1])

    # 1. 지도 그리기
    with col_map:
        st.subheader(f"🗺️ 서울시 {selected_name} 지도")
        
        center_lat, center_lon, zoom = 37.5665, 126.9780, 9.5
        map_data = gdf.copy()

        if selected_district != '전체 서울시':
            map_data = gdf[gdf['자치구명'] == selected_district]
            center_lat = map_data.geometry.centroid.y.values[0]
            center_lon = map_data.geometry.centroid.x.values[0]
            zoom = 11.0

        fig_map = px.choropleth_mapbox(
            map_data,
            geojson=map_data.geometry.__geo_interface__,
            locations=map_data.index,
            color=selected_col,
            mapbox_style="carto-positron",
            zoom=zoom,
            center={"lat": center_lat, "lon": center_lon},
            opacity=0.7,
            hover_name='자치구명',
            hover_data=[selected_col],
            color_continuous_scale=colorscale
        )
        
        # 지하철 관련 지표일 때 점 찍기
        if ('지하철' in selected_name or '대중교통' in selected_name) and not df_stations.empty:
            if 'point_x' in df_stations.columns and 'point_y' in df_stations.columns:
                fig_map.add_trace(go.Scattermapbox(
                    lat=df_stations['point_y'], lon=df_stations['point_x'],
                    mode='markers', marker=go.scattermapbox.Marker(size=5, color='red'),
                    name='지하철역 위치'
                ))

        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
        st.plotly_chart(fig_map, use_container_width=True)

    # 2. 그래프 그리기
    with col_chart:
        st.subheader(f"📊 {selected_name} 순위 비교")
        
        sort_opt = st.radio("정렬 기준:", ["상위", "하위"], horizontal=True, key="chart_sort")
        
        if sort_opt == "상위":
            df_sorted = gdf.sort_values(by=selected_col, ascending=False).head(display_count)
        else:
            df_sorted = gdf.sort_values(by=selected_col, ascending=True).head(display_count)
            
        # 선택된 자치구 강조
        df_sorted['color'] = df_sorted['자치구명'].apply(lambda x: '#FF4B4B' if x == selected_district else '#8884d8')
        
        fig_bar = px.bar(
            df_sorted, x='자치구명', y=selected_col, 
            text=selected_col, color='color', color_discrete_map='identity'
        )
        
        fmt = '%{text:.0f}' if '순위' in selected_name or '인구' in selected_name else '%{text:.2f}'
        fig_bar.update_traces(texttemplate=fmt, textposition='outside')
        fig_bar.update_layout(
            showlegend=False, xaxis_title=None, height=500, margin={"r":0,"t":20,"l":0,"b":0}
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # 3. 데이터 표
    st.markdown("---")
    st.subheader("📋 상세 데이터 표")
    cols_to_show = ['자치구명'] + list(valid_metrics.values())
    
    df_table = gdf[cols_to_show].sort_values(by=selected_col, ascending=(sort_opt=="하위")).head(display_count)
    st.dataframe(df_table, use_container_width=True, hide_index=True)
    
    csv = gdf[cols_to_show].to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 전체 데이터 다운로드 (CSV)", csv, "seoul_analysis.csv", "text/csv")

else:
    st.warning("분석할 데이터가 없습니다. data 폴더에 파일을 확인해주세요.")
