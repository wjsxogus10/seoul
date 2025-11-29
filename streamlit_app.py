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
    # -----------------------------------------------------------
    # (A) 지도 데이터 (인터넷 공공 데이터)
    # -----------------------------------------------------------
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326)
        
        # 지도 데이터의 자치구 이름 컬럼 통일 ('name' -> '자치구명')
        if 'name' in gdf.columns:
            gdf = gdf.rename(columns={'name': '자치구명'})
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf = gdf.rename(columns={'SIG_KOR_NM': '자치구명'})
            
        # 면적 계산 (도형 넓이 기반)
        gdf_area = gdf.to_crs(epsg=5179)
        gdf['면적(km²)'] = gdf_area.geometry.area / 1_000_000
    except Exception as e:
        st.error(f"지도 로드 실패: {e}")
        return None

    # -----------------------------------------------------------
    # (B) 사용자 데이터 병합
    # -----------------------------------------------------------
    
    # 1. 상주 인구
    pop_file = './data/서울시 상권분석서비스(상주인구-자치구).csv'
    if os.path.exists(pop_file):
        try:
            df_pop = pd.read_csv(pop_file, encoding='cp949')
            # '자치구_코드_명' -> '자치구명'으로 변경 후 병합
            df_grp = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
            df_grp = df_grp.rename(columns={'자치구_코드_명': '자치구명'})
            gdf = gdf.merge(df_grp, on='자치구명', how='left')
            gdf['인구 밀도'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
        except: pass

    # 2. 집객시설 수
    biz_file = './data/서울시 상권분석서비스(집객시설-자치구).csv'
    if os.path.exists(biz_file):
        try:
            df_biz = pd.read_csv(biz_file, encoding='cp949')
            df_grp = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
            df_grp = df_grp.rename(columns={'자치구_코드_명': '자치구명'})
            gdf = gdf.merge(df_grp, on='자치구명', how='left')
        except: pass

    # 3. 버스정류장 밀도
    bus_file = './data/GGD_StationInfo_M.xlsx'
    if os.path.exists(bus_file):
        try:
            from shapely.geometry import Point
            df = pd.read_excel(bus_file)
            df = df.dropna(subset=['X', 'Y'])
            geom = [Point(xy) for xy in zip(df['X'], df['Y'])]
            gdf_bus = geopandas.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")
            joined = geopandas.sjoin(gdf_bus, gdf, how="inner", predicate="within")
            cnt = joined.groupby('자치구명').size().reset_index(name='버스정류장_수')
            gdf = gdf.merge(cnt, on='자치구명', how='left')
            gdf['버스정류장_수'] = gdf['버스정류장_수'].fillna(0)
            gdf['버스정류장 밀도'] = gdf['버스정류장_수'] / gdf['면적(km²)']
        except: pass

    # 4. [수정됨] 지하철 밀도 (컬럼명 정확히 지정)
    # 업로드해주신 파일명 그대로 사용
    subway_file = 'seoul_subway_density.xlsx - Sheet1.csv'
    subway_path = f'./data/{subway_file}'
    
    if os.path.exists(subway_path):
        try:
            # CSV 읽기 (인코딩 자동 시도)
            try:
                df_sub = pd.read_csv(subway_path, encoding='utf-8')
            except:
                df_sub = pd.read_csv(subway_path, encoding='cp949')
            
            # [핵심 수정] 파일의 컬럼 이름을 정확하게 지정해서 가져옵니다
            # 파일 컬럼: ['자치구_코드_명', '면적(km²)', '지하철역_수', '지하철역_밀도(개/km²)']
            
            # 1. 필요한 컬럼만 딱 자르기
            # 만약 컬럼명이 조금 다를 수도 있으니, '자치구'와 '밀도' 글자가 포함된 컬럼을 찾습니다.
            gu_col = next((c for c in df_sub.columns if '자치구' in c), None) # '자치구_코드_명' 찾기
            density_col = next((c for c in df_sub.columns if '밀도' in c), None) # '지하철역_밀도(개/km²)' 찾기
            
            if gu_col and density_col:
                # 2. 지도 데이터와 합치기 위해 이름 변경 ('자치구명', '지하철역 밀도')
                df_sub = df_sub.rename(columns={gu_col: '자치구명', density_col: '지하철역 밀도'})
                
                # 3. 병합 (merge)
                gdf = gdf.merge(df_sub[['자치구명', '지하철역 밀도']], on='자치구명', how='left')
                
                # 4. 결측치 0 처리
                gdf['지하철역 밀도'] = gdf['지하철역 밀도'].fillna(0)
                
            else:
                st.sidebar.error(f"❌ 지하철 파일 컬럼 인식 실패: {list(df_sub.columns)}")
                gdf['지하철역 밀도'] = 0
                
        except Exception as e:
            st.sidebar.error(f"지하철 파일 읽기 오류: {e}")
            gdf['지하철역 밀도'] = 0
    else:
        # 파일이 없으면
        gdf['지하철역 밀도'] = 0

    # 5. 교통 부족 순위 계산
    # (버스 밀도와 지하철 밀도가 모두 있어야 계산 가능)
    if '버스정류장 밀도' in gdf.columns and '지하철역 밀도' in gdf.columns:
        # 두 밀도를 더해서 낮을수록(부족할수록) 순위가 1등이 되도록 함
        total_density = gdf['버스정류장 밀도'] + gdf['지하철역 밀도']
        gdf['교통 부족 순위'] = total_density.rank(ascending=True, method='min')

    return gdf

# --------------------------------------------------------------------------
# 3. 화면 구성
# --------------------------------------------------------------------------
gdf = load_and_merge_data()

if gdf is not None:
    st.sidebar.header("🔍 분석 옵션")
    
    # 지표 목록 (요청하신 순서)
    metrics_order = [
        ('상주 인구', '총_상주인구_수'),
        ('인구 밀도', '인구 밀도'),
        ('집객시설 수', '집객시설_수'),
        ('버스정류장 밀도', '버스정류장 밀도'),
        ('지하철역 밀도', '지하철역 밀도'),
        ('교통 부족 순위', '교통 부족 순위')
    ]
    
    # 데이터가 있는 지표만 필터링
    valid_metrics = {k: v for k, v in metrics_order if v in gdf.columns}
    
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
        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
        st.plotly_chart(fig, use_container_width=True)

        # (2) 그래프
        st.subheader(f"📊 {selected_name} 순위")
        col1, col2 = st.columns([3, 1])
        with col2:
            sort_opt = st.radio("정렬:", ["상위", "하위"], horizontal=True)
        
        # 정렬
        if sort_opt == "상위":
            df_sorted = gdf.sort_values(by=selected_col, ascending=False).head(display_count)
        else:
            df_sorted = gdf.sort_values(by=selected_col, ascending=True).head(display_count)
            
        df_sorted['color'] = df_sorted['자치구명'].apply(lambda x: '#FF4B4B' if x == selected_district else '#8884d8')
        
        fig_bar = px.bar(df_sorted, x='자치구명', y=selected_col, text=selected_col, color='color', color_discrete_map='identity')
        # 소수점 처리
        fmt = '%{text:.0f}' if '순위' in selected_name or '인구' in selected_name else '%{text:.4f}'
        fig_bar.update_traces(texttemplate=fmt, textposition='outside')
        fig_bar.update_layout(showlegend=False, xaxis_title=None)
        st.plotly_chart(fig_bar, use_container_width=True)

        # (3) 표
        st.markdown("---")
        st.subheader("📋 상세 데이터 표")
        cols_to_show = ['자치구명'] + list(valid_metrics.values())
        st.dataframe(gdf[cols_to_show].sort_values(by=selected_col, ascending=(sort_opt=="하위")).head(display_count), hide_index=True, use_container_width=True)
        
        csv = gdf[cols_to_show].to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 데이터 다운로드", csv, "seoul_data.csv", "text/csv")
        
    else:
        st.warning("데이터가 로드되지 않았습니다. data 폴더의 파일을 확인해주세요.")
else:
    st.error("지도를 불러올 수 없습니다.")
