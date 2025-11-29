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
# 2. 데이터 로드 및 병합
# --------------------------------------------------------------------------
@st.cache_data
def load_and_merge_data():
    # (A) 지도 데이터
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
        return None

    # (B) 사용자 데이터 병합 (기본값 0으로 초기화 -> 파일 없어도 에러 안 나게 함)
    gdf['인구 밀도'] = 0
    gdf['총_상주인구_수'] = 0
    gdf['집객시설 수'] = 0
    gdf['버스정류장 밀도'] = 0
    gdf['버스정류장_수'] = 0
    gdf['지하철역 밀도'] = 0
    gdf['지하철역_수'] = 0
    
    # 1. 상주 인구
    try:
        df_pop = pd.read_csv('./data/서울시 상권분석서비스(상주인구-자치구).csv', encoding='cp949')
        df_grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
        df_grp.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
        gdf = gdf.merge(df_grp, on='자치구명', how='left', suffixes=('', '_new'))
        
        # 병합 후 컬럼 업데이트
        if '총_상주인구_수_new' in gdf.columns:
            gdf['총_상주인구_수'] = gdf['총_상주인구_수_new'].fillna(0)
            gdf['인구 밀도'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
    except: pass

    # 2. 집객시설 수
    try:
        df_biz = pd.read_csv('./data/서울시 상권분석서비스(집객시설-자치구).csv', encoding='cp949')
        df_grp = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
        df_grp.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
        gdf = gdf.merge(df_grp, on='자치구명', how='left', suffixes=('', '_new'))
        
        if '집객시설_수_new' in gdf.columns:
            gdf['집객시설_수'] = gdf['집객시설_수_new'].fillna(0)
    except: pass

    # 3. 버스정류장 밀도
    try:
        from shapely.geometry import Point
        df_bus = pd.read_excel('./data/GGD_StationInfo_M.xlsx')
        df_bus = df_bus.dropna(subset=['X', 'Y'])
        geom = [Point(xy) for xy in zip(df_bus['X'], df_bus['Y'])]
        gdf_bus = geopandas.GeoDataFrame(df_bus, geometry=geom, crs="EPSG:4326")
        joined = geopandas.sjoin(gdf_bus, gdf, how="inner", predicate="within")
        cnt = joined.groupby('자치구명').size().reset_index(name='버스_cnt')
        
        gdf = gdf.merge(cnt, on='자치구명', how='left')
        gdf['버스정류장_수'] = gdf['버스_cnt'].fillna(0)
        gdf['버스정류장 밀도'] = gdf['버스정류장_수'] / gdf['면적(km²)']
    except: pass

    # 4. [핵심] 지하철 밀도 (파일 우선)
    subway_file = 'seoul_subway_density.xlsx - Sheet1.csv'
    subway_path = f'./data/{subway_file}'
    
    if os.path.exists(subway_path):
        try:
            try: df_sub = pd.read_csv(subway_path, encoding='utf-8')
            except: df_sub = pd.read_csv(subway_path, encoding='cp949')

            # 컬럼 찾기
            gu_col = next((c for c in df_sub.columns if '자치구' in c or '구' in c), None)
            dens_col = next((c for c in df_sub.columns if '밀도' in c), None)
            
            if gu_col and dens_col:
                df_sub = df_sub.rename(columns={gu_col: '자치구명', dens_col: '지하철_밀도_new'})
                
                # 병합
                gdf = gdf.merge(df_sub[['자치구명', '지하철_밀도_new']], on='자치구명', how='left')
                gdf['지하철역 밀도'] = gdf['지하철_밀도_new'].fillna(0)
                st.sidebar.success("✅ 지하철 밀도 파일 로드 성공!")
            else:
                st.sidebar.error("❌ 지하철 파일 컬럼 인식 실패")
        except: pass
    else:
        st.sidebar.warning("⚠️ 지하철 밀도 파일이 없습니다.")

    # 5. 교통 부족 순위 (항상 계산)
    # 버스나 지하철 데이터가 없으면 0으로 계산해서라도 순위를 냄
    total_density = gdf['버스정류장 밀도'] + gdf['지하철역 밀도']
    # 밀도가 낮을수록(부족할수록) 1등
    gdf['교통 부족 순위'] = total_density.rank(ascending=True, method='min')

    return gdf

# --------------------------------------------------------------------------
# 3. 화면 구성
# --------------------------------------------------------------------------
gdf = load_and_merge_data()

if gdf is not None:
    st.sidebar.header("🔍 분석 옵션")
    
    # [순서 지정]
    metrics_order = [
        ('상주 인구', '총_상주인구_수'),
        ('인구 밀도', '인구 밀도'),
        ('집객시설 수', '집객시설_수'),
        ('버스정류장 밀도', '버스정류장 밀도'),
        ('지하철역 밀도', '지하철역 밀도'),
        ('교통 부족 순위', '교통 부족 순위')
    ]
    
    # 모든 지표 표시 (데이터 없어도 0으로 표시)
    valid_metrics = {k: v for k, v in metrics_order}
    
    # 지표 선택
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

    # 색상: 부족 순위는 빨간색 계열
    colorscale = 'Reds_r' if '부족' in selected_name else 'YlGnBu'

    fig = px.choropleth_mapbox(
        gdf, geojson=gdf.geometry.__geo_interface__, locations=gdf.index,
        color=selected_col, mapbox_style="carto-positron", zoom=zoom,
        center={"lat": center_lat, "lon": center_lon}, opacity=0.6,
        hover_name='자치구명', hover_data=[selected_col], color_continuous_scale=colorscale
    )
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
    
    # 소수점 처리
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
    st.download_button("📥 데이터 다운로드", csv, "seoul_data.csv", "text/csv")

else:
    st.error("지도를 로드할 수 없습니다.")
