import streamlit as st
import pandas as pd
import geopandas
import plotly.express as px
import plotly.graph_objects as go
import os
import requests
import io
from shapely.geometry import Point

# --------------------------------------------------------------------------
# 1. 페이지 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")

# --------------------------------------------------------------------------
# 2. 데이터 로드 및 병합 함수
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="데이터를 로드하고 분석을 진행합니다...")
def load_and_merge_data():
    # -----------------------------------------------------------
    # (A) 지도 데이터 로드 (가장 중요!)
    # -----------------------------------------------------------
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    gdf = None
    
    try:
        response = requests.get(map_url)
        response.raise_for_status() # 인터넷 연결 확인
        gdf = geopandas.read_file(io.BytesIO(response.content))
        gdf = gdf.to_crs(epsg=4326)
        
        # 자치구명 컬럼 통일
        if 'name' in gdf.columns:
            gdf['자치구명'] = gdf['name']
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf['자치구명'] = gdf['SIG_KOR_NM']
        else:
            return None, "❌ 지도 데이터에 '자치구명' 컬럼이 없습니다."
            
        gdf['면적(km²)'] = gdf.geometry.to_crs(epsg=5179).area / 1_000_000
    except Exception as e:
        return None, f"❌ 지도 다운로드 실패: {e}"

    # -----------------------------------------------------------
    # (B) 사용자 데이터 병합
    # -----------------------------------------------------------
    
    # 컬럼 초기화 (에러 방지용 기본값)
    cols_init = ['총_상주인구_수', '인구 밀도', '집객시설 수', '버스정류장_수', '버스정류장 밀도', '지하철역_수', '지하철역 밀도', '총_교통수단_수', '대중교통 밀도']
    for c in cols_init:
        if c not in gdf.columns:
            gdf[c] = 0

    # 1. 상주 인구
    try:
        df_pop = pd.read_csv('./data/서울시 상권분석서비스(상주인구-자치구).csv', encoding='cp949')
        grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index().rename(columns={'자치구_코드_명':'자치구명'})
        gdf = gdf.merge(grp, on='자치구명', how='left')
        gdf['총_상주인구_수'] = gdf['총_상주인구_수'].fillna(0)
        gdf['인구 밀도'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
    except: pass

    # 2. 집객시설 수
    try:
        df_biz = pd.read_csv('./data/서울시 상권분석서비스(집객시설-자치구).csv', encoding='cp949')
        # 유연하게 컬럼 찾기
        biz_col = next((c for c in df_biz.columns if '집객' in c or '시설' in c), None)
        gu_col = next((c for c in df_biz.columns if '자치구' in c), None)
        if biz_col and gu_col:
            grp = df_biz.groupby(gu_col)[biz_col].mean().reset_index().rename(columns={gu_col:'자치구명', biz_col:'집객시설 수'})
            gdf = gdf.merge(grp, on='자치구명', how='left')
            gdf['집객시설 수'] = gdf['집객시설 수'].fillna(0)
    except: pass

    # 3. 버스정류장 밀도
    try:
        from shapely.geometry import Point
        df_bus = pd.read_excel('./data/GGD_StationInfo_M.xlsx').dropna(subset=['X', 'Y'])
        geom = [Point(xy) for xy in zip(df_bus['X'], df_bus['Y'])]
        # 버스 좌표계 변환 (5181 -> 4326)
        gdf_bus = geopandas.GeoDataFrame(df_bus, geometry=geom, crs="EPSG:5181").to_crs(epsg=4326)
        joined = geopandas.sjoin(gdf_bus, gdf[['자치구명', 'geometry']], how="inner", predicate="within")
        cnt = joined.groupby('자치구명').size().reset_index(name='버스정류장_수')
        
        gdf = gdf.merge(cnt, on='자치구명', how='left')
        gdf['버스정류장_수'] = gdf['버스정류장_수'].fillna(0)
        gdf['버스정류장 밀도'] = gdf['버스정류장_수'] / gdf['면적(km²)']
    except: 
        gdf['버스정류장 밀도'] = 0

    # 4. 지하철 밀도
    try:
        density_file = './data/지하철 밀도.CSV'
        if os.path.exists(density_file):
            try: df_dens = pd.read_csv(density_file, encoding='utf-8')
            except: df_dens = pd.read_csv(density_file, encoding='cp949')
            
            gu_col = next((c for c in df_dens.columns if '자치구' in c), None)
            dens_col = next((c for c in df_dens.columns if '밀도' in c), None)
            
            if gu_col and dens_col:
                rename_map = {gu_col: '자치구명', dens_col: '지하철역 밀도'}
                cnt_col = next((c for c in df_dens.columns if '역' in c and '수' in c), None)
                if cnt_col: rename_map[cnt_col] = '지하철역_수'
                
                df_dens = df_dens.rename(columns=rename_map)
                gdf = gdf.merge(df_dens, on='자치구명', how='left')
                gdf['지하철역 밀도'] = gdf['지하철역 밀도'].fillna(0)
                if '지하철역_수' in gdf.columns:
                    gdf['지하철역_수'] = gdf['지하철역_수'].fillna(0)
    except: pass

    # 5. 지하철 위치 좌표
    df_stations = pd.DataFrame()
    try:
        coord_file = './data/지하철 위경도.CSV'
        if os.path.exists(coord_file):
            try: df_stations = pd.read_csv(coord_file, encoding='utf-8')
            except: df_stations = pd.read_csv(coord_file, encoding='cp949')
            # 컬럼 확인
            x_col = next((c for c in df_stations.columns if c in ['point_x', '경도', 'lon']), None)
            y_col = next((c for c in df_stations.columns if c in ['point_y', '위도', 'lat']), None)
            if x_col and y_col:
                df_stations = df_stations.rename(columns={x_col:'point_x', y_col:'point_y'})
    except: pass

    # 6. 계산
    if '지하철역_수' not in gdf.columns: gdf['지하철역_수'] = 0
    gdf['총_교통수단_수'] = gdf['버스정류장_수'] + gdf['지하철역_수']
    gdf['대중교통 밀도'] = gdf['총_교통수단_수'] / gdf['면적(km²)']
    
    pop_safe = gdf['총_상주인구_수'].replace(0, 1)
    gdf['인구 대비 교통수단 비율'] = gdf['총_교통수단_수'] / pop_safe
    gdf['교통 부족 순위'] = gdf['인구 대비 교통수단 비율'].rank(ascending=True, method='min')

    return gdf, df_stations

# --------------------------------------------------------------------------
# 3. 화면 구성 및 시각화
# --------------------------------------------------------------------------
# 함수 실행 결과 받기
result = load_and_merge_data()

# [핵심] 로드 실패 시 앱 중단 (NoneType 에러 방지)
if result is None or result[0] is None:
    error_msg = result[1] if result and len(result) > 1 else "알 수 없는 오류"
    st.error("🚨 데이터 로드에 실패했습니다!")
    st.error(f"원인: {error_msg}")
    st.info("Tip: requirements.txt에 'requests' 라이브러리가 있는지 확인해주세요.")
    st.stop() # 여기서 코드 실행을 멈춤

gdf, df_stations = result

st.sidebar.header("🔍 분석 옵션")

metrics_order = [
    ('상주 인구', '총_상주인구_수'),
    ('인구 밀도', '인구 밀도'),
    ('집객시설 수', '집객시설 수'),
    ('버스정류장 밀도', '버스정류장 밀도'),
    ('지하철역 밀도', '지하철역 밀도'),
    ('대중교통 밀도 (버스+지하철)', '대중교통 밀도'),
    ('교통 부족 순위 (인구 대비)', '교통 부족 순위')
]

valid_metrics = {}
for k, v in metrics_order:
    if v in gdf.columns:
        valid_metrics[k] = v

if valid_metrics:
    selected_name = st.sidebar.radio("분석할 지표 선택", list(valid_metrics.keys()))
    selected_col = valid_metrics[selected_name]
    
    st.sidebar.markdown("---")
    display_count = st.sidebar.slider("📊 그래프/표 표시 개수", 5, 25, 10)
    st.sidebar.markdown
