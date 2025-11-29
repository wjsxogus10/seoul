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
# 2. 데이터 로드 및 병합 (인터넷 지도 + 내 데이터)
# --------------------------------------------------------------------------
@st.cache_data
def load_and_merge_data():
    # (A) 인터넷에서 서울시 지도 가져오기 (용량 문제 해결)
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    
    try:
        gdf = geopandas.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326)
        
        # 컬럼 이름 통일
        if 'name' in gdf.columns:
            gdf = gdf.rename(columns={'name': '자치구명'})
        elif 'SIG_KOR_NM' in gdf.columns:
            gdf = gdf.rename(columns={'SIG_KOR_NM': '자치구명'})
            
        # 면적 계산
        gdf_area = gdf.to_crs(epsg=5179)
        gdf['면적(km²)'] = gdf_area.geometry.area / 1_000_000
        
    except Exception as e:
        st.error(f"지도를 가져오는 중 오류 발생: {e}")
        return None

    # (B) 내 데이터 파일들 합치기 (csv, xlsx)
    # 1. 인구 데이터
    pop_file = './data/서울시 상권분석서비스(상주인구-자치구).csv'
    if os.path.exists(pop_file):
        try:
            df_pop = pd.read_csv(pop_file, encoding='cp949')
            df_pop_group = df_pop.groupby('자치구_코드_명')['총_상주인구_수'].mean().reset_index()
            df_pop_group.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
            gdf = gdf.merge(df_pop_group, on='자치구명', how='left')
            gdf['인구_밀도(명/km²)'] = gdf['총_상주인구_수'] / gdf['면적(km²)']
        except: pass

    # 2. 상권 데이터
    biz_file = './data/서울시 상권분석서비스(집객시설-자치구).csv'
    if os.path.exists(biz_file):
        try:
            df_biz = pd.read_csv(biz_file, encoding='cp949')
            df_biz_group = df_biz.groupby('자치구_코드_명')['집객시설_수'].mean().reset_index()
            df_biz_group.rename(columns={'자치구_코드_명': '자치구명'}, inplace=True)
            gdf = gdf.merge(df_biz_group, on='자치구명', how='left')
        except: pass

    # 3. 교통 데이터
    station_file = './data/GGD_StationInfo_M.xlsx'
    if os.path.exists(station_file):
        try:
            df_station = pd.read_excel(station_file)
            df_station = df_station.dropna(subset=['X', 'Y'])
            geometry = [Point(xy) for xy in zip(df_station['X'], df_station['Y'])]
            gdf_station = geopandas.GeoDataFrame(df_station, geometry=geometry, crs="EPSG:4326")
            joined = geopandas.sjoin(gdf_station, gdf, how="inner", predicate="within")
            station_counts = joined.groupby('자치구명').size().reset_index(name='정류장_수')
            gdf = gdf.merge(station_counts, on='자치구명', how='left')
            gdf['정류장_밀도(개/km²)'] = gdf['정류장_수'] / gdf['면적(km²)']
            gdf['정류장_수'] = gdf['정류장_수'].fillna(0)
            
            # 부족 순위 (적을수록 1등)
            gdf['교통_부족_순위'] = gdf['정류장_수'].rank(ascending=True, method='min')
        except: pass

    return gdf

# --------------------------------------------------------------------------
# 3. 화면 구성 (지도 + 그래프 + 표)
# --------------------------------------------------------------------------
gdf = load_and_merge_data()

if gdf is not None:
    # --- 사이드바 설정 ---
    st.sidebar.header("🔍 분석 옵션")
    
    # 보고 싶은 지표 선택
    metrics = {
        '인구 밀도': '인구_밀도(명/km²)',
        '총 상주인구': '총_상주인구_수',
        '집객시설 수': '집객시설_수',
        '정류장 수': '정류장_수',
        '교통 부족 순위': '교통_부족_순위'
    }
    available_metrics = {k: v for k, v in metrics.items() if v in gdf.columns}
    
    if available_metrics:
        selected_metric_name = st.sidebar.radio("분석할 지표 선택", list(available_metrics.keys()))
        selected_col = available_metrics[selected_metric_name]
        
        # 자치구 선택 기능
        district_list = ['전체 서울시'] + sorted(gdf['자치구명'].unique().tolist())
        selected_district = st.sidebar.selectbox("자치구 상세 보기", district_list)

        # -------------------------------------------------------
        # (1) 지도 시각화
        # -------------------------------------------------------
        st.subheader(f"🗺️ 서울시 {selected_metric_name} 지도")
        
        center_lat, center_lon = 37.5665, 126.9780
        zoom_level = 9.5
        
        if selected_district != '전체 서울시':
            district_geo = gdf[gdf['자치구명'] == selected_district]
            center_lat = district_geo.geometry.centroid.y.values[0]
            center_lon = district_geo.geometry.centroid.x.values[0]
            zoom_level = 11.5

        fig_map = px.choropleth_mapbox(
            gdf,
            geojson=gdf.geometry.__geo_interface__,
            locations=gdf.index,
            color=selected_col,
            mapbox_style="carto-positron",
            zoom=zoom_level,
            center={"lat": center_lat, "lon": center_lon},
            opacity=0.6,
            hover_name='자치구명',
            hover_data=[selected_col],
            color_continuous_scale='YlGnBu'
        )
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
        st.plotly_chart(fig_map, use_container_width=True)

        # -------------------------------------------------------
        # (2) 통계 & 그래프
        # -------------------------------------------------------
        st.markdown("---")
        
        # 상세 정보 카드
        if selected_district != '전체 서울시':
            st.subheader(f"📍 {selected_district} 분석 결과")
            target_row = gdf[gdf['자치구명'] == selected_district].iloc[0]
            val = target_row[selected_col]
            avg = gdf[selected_col].mean()
            col1, col2, col3 = st.columns(3)
            col1.metric("선택한 지표 값", f"{val:,.1f}")
            col2.metric("서울시 평균", f"{avg:,.1f}")
            col3.metric("평균 대비 차이", f"{val - avg:,.1f}")

        # 막대 차트
        st.subheader(f"📊 {selected_metric_name} 순위 비교")
        col_chart1, col_chart2 = st.columns([3, 1])
        with col_chart2:
            sort_order = st.radio("정렬 기준:", ["상위 10개", "하위 10개", "전체 보기"])
        
        df_sorted = gdf[['자치구명', selected_col]].sort_values(by=selected_col, ascending=False)
        
        if sort_order == "상위 10개":
            chart_data = df_sorted.head(10)
        elif sort_order == "하위 10개":
            chart_data = df_sorted.tail(10).sort_values(by=selected_col, ascending=True)
        else:
            chart_data = df_sorted

        chart_data['색상'] = chart_data['자치구명'].apply(lambda x: 'red' if x == selected_district else 'blue')
        
        fig_bar = px.bar(
            chart_data,
            x='자치구명',
            y=selected_col,
            color='색상',
            color_discrete_map={'red': '#FF4B4B', 'blue': '#8884d8'},
            title=f"{selected_metric_name} 순위"
        )
        fig_bar.update_layout(showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)

        # -------------------------------------------------------
        # (3) [NEW] 상세 데이터 표 (여기가 추가됨!)
        # -------------------------------------------------------
        st.markdown("---")
        st.subheader("📋 전체 자치구 상세 데이터 표")
        
        # 표에 보여줄 컬럼 정리 (이름 + 모든 지표)
        cols_to_show = ['자치구명'] + list(available_metrics.values())
        df_table = gdf[cols_to_show].copy()
        
        # 선택한 지표 기준으로 내림차순 정렬
        df_table = df_table.sort_values(by=selected_col, ascending=False)
        
        # 대화형 표 보여주기
        st.dataframe(
            df_table, 
            use_container_width=True,
            hide_index=True
        )
        
        # 엑셀 다운로드 버튼
        csv = df_table.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 표 데이터 다운로드 (CSV)",
            data=csv,
            file_name=f"seoul_{selected_metric_name}_data.csv",
            mime='text/csv'
        )

    else:
        st.warning("데이터 파일이 없어 지도만 표시됩니다.")
        st.info("data 폴더에 파일을 업로드해주세요.")
else:
    st.error("지도를 로드할 수 없습니다.")
