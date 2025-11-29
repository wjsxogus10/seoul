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
# 2. 데이터 로드 및 병합 (스마트 탐지 기능 탑재)
# --------------------------------------------------------------------------
@st.cache_data
def load_and_merge_data():
    # (A) 지도 데이터 다운로드
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

    # (B) data 폴더 파일 자동 스캔
    data_dir = './data'
    if not os.path.exists(data_dir):
        st.error("❌ 'data' 폴더가 없습니다.")
        return gdf, pd.DataFrame()

    files = [f for f in os.listdir(data_dir) if f.endswith('.csv') or f.endswith('.xlsx')]
    
    # 병합용 임시 변수들
    df_stations = pd.DataFrame() # 점 찍기용 좌표 데이터
    
    # 기본값 초기화
    gdf['인구 밀도'] = 0
    gdf['총_상주인구_수'] = 0
    gdf['집객시설 수'] = 0
    gdf['버스정류장 밀도'] = 0
    gdf['지하철역 밀도'] = 0
    
    # -------------------------------------------------------
    # [핵심] 모든 파일을 하나씩 열어보고 정체 파악하기
    # -------------------------------------------------------
    for f in files:
        file_path = os.path.join(data_dir, f)
        try:
            # 파일 읽기
            if f.endswith('.csv'):
                try: df = pd.read_csv(file_path, encoding='utf-8')
                except: df = pd.read_csv(file_path, encoding='cp949')
            else:
                df = pd.read_excel(file_path)

            cols = df.columns.tolist()
            
            # 1. 지하철 밀도 파일인지 확인 ('밀도'라는 글자가 컬럼에 있는지)
            density_col = next((c for c in cols if '지하철' in c and '밀도' in c), None)
            gu_col = next((c for c in cols if '자치구' in c or '구' in c), None)
            
            if density_col and gu_col:
                # 찾았다! 병합 진행
                temp = df[[gu_col, density_col]].copy()
                temp = temp.rename(columns={gu_col: '자치구명', density_col: '지하철역 밀도'})
                # 숫자 변환 (콤마 제거 등)
                if temp['지하철역 밀도'].dtype == object:
                    temp['지하철역 밀도'] = pd.to_numeric(temp['지하철역 밀도'].str.replace(',', ''), errors='coerce')
                
                # 기존 값 덮어쓰기 방지 (우선순위 병합)
                if '지하철역 밀도' in gdf.columns and gdf['지하철역 밀도'].sum() == 0:
                    gdf = gdf.drop(columns=['지하철역 밀도']) # 0으로 된 컬럼 삭제 후 다시 병합
                    gdf = gdf.merge(temp, on='자치구명', how='left')
                    gdf['지하철역 밀도'] = gdf['지하철역 밀도'].fillna(0)
                    st.toast(f"✅ 지하철 밀도 데이터 로드: {f}", icon="🚇")
                continue

            # 2. 지하철 좌표 파일인지 확인 ('point_x' 또는 '위도'가 있는지)
            if ('point_x' in cols) or ('위도' in cols) or ('lon' in cols):
                # 좌표 컬럼 통일
                x_c = next((c for c in cols if c in ['point_x', '경도', 'lon', 'X']), None)
                y_c = next((c for c in cols if c in ['point_y', '위도', 'lat', 'Y']), None)
                if x_c and y_c:
                    temp = df.copy()
                    temp = temp.rename(columns={x_c: 'point_x', y_c: 'point_y'})
                    df_stations = temp # 좌표 데이터 저장
                continue

            # 3. 인구 데이터 확인
            if '총_상주인구_수' in cols:
                temp = df.groupby(gu_col)['총_상주인구_수'].mean().reset_index()
                temp = temp.rename(columns={gu_col: '자치구명'})
                gdf = gdf.drop(columns=['총_상주인구_수', '인구 밀도'], errors='ignore') # 초기화
                gdf = gdf.merge(temp, on='자치구명', how='left')
                gdf['인구 밀도'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
                continue

            # 4. 상권 데이터 확인
            if '집객시설_수' in cols:
                temp = df.groupby(gu_col)['집객시설_수'].mean().reset_index()
                temp = temp.rename(columns={gu_col: '자치구명'})
                gdf = gdf.drop(columns=['집객시설 수'], errors='ignore')
                gdf = gdf.merge(temp, on='자치구명', how='left')
                continue

        except:
            continue

    # 5. 버스 정류장 (파일 이름으로 찾기 - 보통 형식이 고정됨)
    bus_file = './data/GGD_StationInfo_M.xlsx'
    if os.path.exists(bus_file) and gdf['버스정류장 밀도'].sum() == 0:
        try:
            from shapely.geometry import Point
            df_bus = pd.read_excel(bus_file).dropna(subset=['X', 'Y'])
            geom = [Point(xy) for xy in zip(df_bus['X'], df_bus['Y'])]
            gdf_bus = geopandas.GeoDataFrame(df_bus, geometry=geom, crs="EPSG:4326")
            joined = geopandas.sjoin(gdf_bus, gdf, how="inner", predicate="within")
            cnt = joined.groupby('자치구명').size().reset_index(name='버스정류장_수')
            gdf = gdf.merge(cnt, on='자치구명', how='left')
            gdf['버스정류장 밀도'] = gdf['버스정류장_수'].fillna(0) / gdf['면적(km²)']
        except: pass

    # 6. 교통 부족 순위 (밀도가 0이면 순위 계산 안됨 -> 파일 없으면 0)
    # 버스 밀도와 지하철 밀도를 합쳐서, 낮을수록(부족할수록) 1등
    total_transport = gdf['버스정류장 밀도'].fillna(0) + gdf['지하철역 밀도'].fillna(0)
    gdf['교통 부족 순위'] = total_transport.rank(ascending=True, method='min')

    return gdf, df_stations

# --------------------------------------------------------------------------
# 3. 화면 구성
# --------------------------------------------------------------------------
result = load_and_merge_data()
if result is None or result[0] is None:
    st.error("데이터 로드 중 치명적인 오류가 발생했습니다.")
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

# 데이터가 있는 지표만 메뉴에 표시
valid_metrics = {}
for k, v in metrics_order:
    if v in gdf.columns:
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
    
    # [Point] 지하철 관련 지표일 때 역 위치 점 찍기
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
    st.download_button("📥 전체 데이터 다운로드 (CSV)", csv, "seoul_analysis.csv", "text/csv")

else:
    st.warning("분석할 데이터가 없습니다. data 폴더에 csv/xlsx 파일을 올려주세요.")
