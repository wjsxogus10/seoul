import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import os
from shapely.geometry import Point

# --------------------------------------------------------------------------
# 페이지 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="서울시 도시계획 대시보드")
st.title("🏙️ 서울시 도시계획 및 대중교통 개선 대시보드")

# --------------------------------------------------------------------------
# 유틸 함수: 안전한 파일 읽기 (utf-8 -> cp949 fallback)
# --------------------------------------------------------------------------
def safe_read_csv(path):
    try:
        return pd.read_csv(path, encoding='utf-8')
    except Exception:
        try:
            return pd.read_csv(path, encoding='cp949')
        except Exception:
            return None

def safe_read_excel(path):
    try:
        return pd.read_excel(path)
    except Exception:
        return None

# --------------------------------------------------------------------------
# 2. 데이터 로드 및 병합 함수 (Robust + Defensive)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="데이터를 로드하고 분석을 진행합니다...")
def load_and_merge_data():
    # --- 1) 기본 지도(GeoJSON) 로드 ---
    map_url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
    try:
        gdf = gpd.read_file(map_url)
        gdf = gdf.to_crs(epsg=4326)
    except Exception as e:
        # 지도 로드 실패
        return None, None

    # 자치구명 보정
    if 'name' in gdf.columns:
        gdf['자치구명'] = gdf['name']
    elif 'SIG_KOR_NM' in gdf.columns:
        gdf['자치구명'] = gdf['SIG_KOR_NM']
    else:
        # 치명적: 자치구명 없으면 중단
        return None, None

    # 면적 계산 (km^2) — 투영 후 면적
    try:
        gdf['면적(km²)'] = gdf.geometry.to_crs(epsg=5179).area / 1_000_000
    except Exception:
        gdf['면적(km²)'] = None

    # --- 2) 기본 컬럼 초기화(방어적) ---
    desired_cols = [
        '총_상주인구_수', '인구 밀도', '집객시설 수',
        '버스정류장_수', '버스정류장 밀도',
        '지하철역_수', '지하철역 밀도',
        '총_교통수단_수', '대중교통 밀도',
        '인구 대비 교통수단 비율', '교통 부족 순위'
    ]
    for c in desired_cols:
        if c not in gdf.columns:
            gdf[c] = 0

    # --- 3) 상주 인구 병합(파일명 가정) ---
    pop_path = './data/서울시 상권분석서비스(상주인구-자치구).csv'
    if os.path.exists(pop_path):
        try:
            df_pop = safe_read_csv(pop_path)
            if df_pop is not None:
                gu_col = next((c for c in df_pop.columns if '자치구' in c), None)
                pop_col = next((c for c in df_pop.columns if '상주인구' in c or '총_상주인구' in c), None)
                if gu_col and pop_col:
                    grp = df_pop.groupby(gu_col)[pop_col].mean().reset_index()
                    grp = grp.rename(columns={gu_col:'자치구명', pop_col:'총_상주인구_수'})
                    gdf = gdf.merge(grp, on='자치구명', how='left')
                    gdf['총_상주인구_수'] = gdf['총_상주인구_수'].fillna(0)
                    # 인구 밀도 계산 (면적 0 방지)
                    gdf['인구 밀도'] = gdf.apply(lambda r: r['총_상주인구_수'] / r['면적(km²)'] if r['면적(km²)'] and r['면적(km²)']>0 else 0, axis=1)
        except Exception:
            pass

    # --- 4) 집객시설 수 병합 ---
    biz_path = './data/서울시 상권분석서비스(집객시설-자치구).csv'
    if os.path.exists(biz_path):
        try:
            df_biz = safe_read_csv(biz_path)
            if df_biz is not None:
                biz_count_col = next((c for c in df_biz.columns if '집객시설' in c or '시설수' in c or '집객' in c), None)
                gu_col_biz = next((c for c in df_biz.columns if '자치구' in c), None)
                if biz_count_col and gu_col_biz:
                    grp = df_biz.groupby(gu_col_biz)[biz_count_col].mean().reset_index()
                    grp = grp.rename(columns={gu_col_biz:'자치구명', biz_count_col:'집객시설 수'})
                    gdf = gdf.merge(grp, on='자치구명', how='left')
                    gdf['집객시설 수'] = gdf['집객시설 수'].fillna(0)
        except Exception:
            pass

    # --- 5) 지하철 데이터 병합 (유연 처리) ---
    subway_path = './data/지하철 위경도.CSV'
    subway_count_from_file = None
    if os.path.exists(subway_path):
        try:
            df_sub = safe_read_csv(subway_path)
            if df_sub is not None:
                # 가능성 있는 위경도/자치구/개수 컬럼 자동 탐지
                lon_candidates = ['point_x', 'X', '경도', 'lon', 'longitude']
                lat_candidates = ['point_y', 'Y', '위도', 'lat', 'latitude']
                gu_candidates = ['자치구', '자치구_코드_명', '자치구명', '자치구명.1', 'gu', '구']

                lon_col = next((c for c in df_sub.columns if c in lon_candidates), None)
                lat_col = next((c for c in df_sub.columns if c in lat_candidates), None)
                gu_col_sub = next((c for c in df_sub.columns if any(k in c for k in gu_candidates)), None)
                count_col = next((c for c in df_sub.columns if '지하철역_수' in c or '지하철역수' in c or '지하철역' in c and '밀도' not in c), None)

                # 컬럼명 표준화
                if gu_col_sub:
                    df_sub = df_sub.rename(columns={gu_col_sub: '자치구명'})
                if count_col:
                    df_sub = df_sub.rename(columns={count_col: '지하철역_수'})

                # (A) 위경도 정보가 있으면 공간조인으로 집계
                if lon_col and lat_col:
                    df_sub = df_sub.dropna(subset=[lon_col, lat_col])
                    try:
                        geom = [Point(xy) for xy in zip(df_sub[lon_col].astype(float), df_sub[lat_col].astype(float))]
                        gdf_sub = gpd.GeoDataFrame(df_sub, geometry=geom, crs="EPSG:4326")
                        # 공간조인 (points within polygons)
                        joined = gpd.sjoin(gdf_sub, gdf[['자치구명', 'geometry']], how='left', predicate='within')
                        cnt = joined.groupby('자치구명').size().reset_index(name='지하철역_수')
                        subway_count_from_file = cnt
                    except Exception:
                        subway_count_from_file = None

                # (B) 좌표 없지만 파일에 이미 집계된 '자치구별 지하철역 수'가 있다면 사용
                if subway_count_from_file is None and '자치구명' in df_sub.columns and '지하철역_수' in df_sub.columns:
                    cnt = df_sub.groupby('자치구명')['지하철역_수'].sum().reset_index()
                    subway_count_from_file = cnt

        except Exception:
            subway_count_from_file = None

    # merge subway counts if available
    if subway_count_from_file is not None:
        try:
            subway_count_from_file['자치구명'] = subway_count_from_file['자치구명'].astype(str)
            gdf['자치구명'] = gdf['자치구명'].astype(str)
            gdf = gdf.merge(subway_count_from_file, on='자치구명', how='left')
            gdf['지하철역_수'] = gdf['지하철역_수'].fillna(0)
        except Exception:
            gdf['지하철역_수'] = gdf.get('지하철역_수', 0).fillna(0)

    # --- 6) 버스 정류장 데이터 병합 (유연 처리) ---
    bus_paths = ['./data/GGD_StationInfo_M.xlsx', './data/버스정류장.xlsx', './data/버스정류장.csv']
    bus_count_from_file = None
    for p in bus_paths:
        if os.path.exists(p):
            try:
                if p.endswith('.xlsx') or p.endswith('.xls'):
                    df_bus = safe_read_excel(p)
                else:
                    df_bus = safe_read_csv(p)
                if df_bus is None:
                    continue

                lon_candidates = ['X', 'lon', '경도', 'longitude', 'point_x']
                lat_candidates = ['Y', 'lat', '위도', 'latitude', 'point_y']
                lon_col = next((c for c in df_bus.columns if c in lon_candidates), None)
                lat_col = next((c for c in df_bus.columns if c in lat_candidates), None)
                gu_col_bus = next((c for c in df_bus.columns if '자치구' in c or '구' == c), None)
                count_col = next((c for c in df_bus.columns if '정류장' in c or '버스' in c and '수' in c), None)

                if lon_col and lat_col:
                    df_bus = df_bus.dropna(subset=[lon_col, lat_col])
                    geom = [Point(xy) for xy in zip(df_bus[lon_col].astype(float), df_bus[lat_col].astype(float))]
                    gdf_bus = gpd.GeoDataFrame(df_bus, geometry=geom, crs="EPSG:4326")
                    joined = gpd.sjoin(gdf_bus, gdf[['자치구명', 'geometry']], how='left', predicate='within')
                    cnt = joined.groupby('자치구명').size().reset_index(name='버스정류장_수')
                    bus_count_from_file = cnt
                elif gu_col_bus and count_col:
                    cnt = df_bus.groupby(gu_col_bus)[count_col].sum().reset_index()
                    cnt = cnt.rename(columns={gu_col_bus:'자치구명', count_col:'버스정류장_수'})
                    bus_count_from_file = cnt

                if bus_count_from_file is not None:
                    break
            except Exception:
                continue

    # merge bus counts if available
    if bus_count_from_file is not None:
        try:
            bus_count_from_file['자치구명'] = bus_count_from_file['자치구명'].astype(str)
            gdf['자치구명'] = gdf['자치구명'].astype(str)
            gdf = gdf.merge(bus_count_from_file, on='자치구명', how='left')
            gdf['버스정류장_수'] = gdf['버스정류장_수'].fillna(0)
        except Exception:
            gdf['버스정류장_수'] = gdf.get('버스정류장_수', 0).fillna(0)
    else:
        gdf['버스정류장_수'] = gdf.get('버스정류장_수', 0).fillna(0)

    # --- 7) 지하철/버스 밀도 계산(면적 0 체크) ---
    def safe_density(count, area):
        try:
            return count / area if area and area > 0 else 0
        except Exception:
            return 0

    gdf['버스정류장 밀도'] = gdf.apply(lambda r: safe_density(r.get('버스정류장_수', 0), r.get('면적(km²)', 0)), axis=1)
    gdf['지하철역 밀도'] = gdf.apply(lambda r: safe_density(r.get('지하철역_수', 0), r.get('면적(km²)', 0)), axis=1)

    # --- 8) 총 교통수단 / 대중교통 밀도 / 인구 대비 비율 / 부족 순위 ---
    # 방어: 존재하지 않는 컬럼에 기본값 설정
    for c in ['버스정류장_수', '지하철역_수', '총_상주인구_수']:
        if c not in gdf.columns:
            gdf[c] = 0
    gdf['총_교통수단_수'] = gdf['버스정류장_수'].fillna(0) + gdf['지하철역_수'].fillna(0)
    gdf['대중교통 밀도'] = gdf.apply(lambda r: safe_density(r['총_교통수단_수'], r.get('면적(km²)', 0)), axis=1)

    population_safe = gdf['총_상주인구_수'].replace(0, pd.NA)
    # 인구가 0이면 분모를 1로 치환하여 무한대/NaN 방지
    gdf['인구 대비 교통수단 비율'] = gdf.apply(lambda r: r['총_교통수단_수'] / (r['총_상주인구_수'] if r['총_상주인구_수'] and r['총_상주인구_수']>0 else 1), axis=1)
    gdf['교통 부족 순위'] = gdf['인구 대비 교통수단 비율'].rank(ascending=True, method='min')

    # 일부 컬럼 타입 정리 (숫자형)
    num_cols = ['총_상주인구_수', '인구 밀도', '집객시설 수',
                '버스정류장_수', '버스정류장 밀도',
                '지하철역_수', '지하철역 밀도',
                '총_교통수단_수', '대중교통 밀도', '인구 대비 교통수단 비율', '교통 부족 순위']
    for c in num_cols:
        try:
            gdf[c] = pd.to_numeric(gdf[c], errors='coerce').fillna(0)
        except Exception:
            pass

    # 빈 stations DataFrame (필요하면 리턴에 포함)
    df_stations = pd.DataFrame()
    return gdf, df_stations

# --------------------------------------------------------------------------
# 3. 화면 구성 및 시각화
# --------------------------------------------------------------------------
result = load_and_merge_data()
if result is None or result[0] is None:
    st.error("❌ GeoJSON 지도 로드 또는 필수 데이터 로드에 실패했습니다. (네트워크/파일 경로를 확인하세요)")
    st.stop()

gdf, df_stations = result

st.sidebar.header("🔍 분석 옵션")

# 지표 설정 (표시될 이름 : 컬럼명)
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
        # 순위는 값이 0이어도 의미가 있으므로 포함
        if gdf[v].sum() > 0 or '순위' in k:
            valid_metrics[k] = v

if not valid_metrics:
    st.warning("사용 가능한 지표가 없습니다.")
    st.stop()

# 1) 지표 선택
selected_name = st.sidebar.radio("분석할 지표 선택", list(valid_metrics.keys()))
selected_col = valid_metrics[selected_name]

st.sidebar.markdown("---")
# 2) 개수 조절
display_count = st.sidebar.slider("📊 그래프/표 표시 개수", 5, 25, 10)
st.sidebar.markdown("---")
# 3) 자치구 선택
district_list = ['전체 서울시'] + sorted(gdf['자치구명'].astype(str).unique().tolist())
selected_district = st.sidebar.selectbox("자치구 상세 보기", district_list)

# 색상스케일
colorscale = 'Blues' if selected_col in ['총_상주인구_수', '인구 밀도', '집객시설 수'] else 'Reds'

# 레이아웃: 지도 + 그래프
col_map, col_chart = st.columns([1, 1])

with col_map:
    st.subheader(f"🗺️ 서울시 {selected_name} 지도")

    center_lat, center_lon, zoom = 37.5665, 126.9780, 9.5
    map_data = gdf.copy()

    if selected_district != '전체 서울시':
        map_data = gdf[gdf['자치구명'] == selected_district]
        # centroid 계산 안전성
        try:
            center_lat = float(map_data.geometry.centroid.y.values[0])
            center_lon = float(map_data.geometry.centroid.x.values[0])
            zoom = 11.0
        except Exception:
            center_lat, center_lon, zoom = 37.5665, 126.9780, 9.5

    # plotly choropleth_mapbox 사용
    try:
        fig = px.choropleth_mapbox(
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
        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error("지도를 그리는 중 오류가 발생했습니다.")
        st.exception(e)

with col_chart:
    st.subheader(f"📊 {selected_name} 순위 비교")
    sort_opt = st.radio("정렬 기준:", ["상위", "하위"], horizontal=True, key="sort_chart")
    ascending = False if sort_opt == "상위" else True
    df_sorted = gdf.sort_values(by=selected_col, ascending=ascending).head(display_count).copy()

    # 강조 색상
    df_sorted['__color__'] = df_sorted['자치구명'].apply(lambda x: '#FF4B4B' if x == selected_district else '#8884d8')

    fig_bar = px.bar(df_sorted, x='자치구명', y=selected_col, text=selected_col, color='__color__', color_discrete_map='identity')
    fmt = '%{text:.0f}' if '순위' in selected_name or '인구' in selected_name else '%{text:.4f}'
    fig_bar.update_traces(texttemplate=fmt, textposition='outside')
    fig_bar.update_layout(showlegend=False, xaxis_title=None, height=500, margin={"r":0,"t":20,"l":0,"b":0})
    st.plotly_chart(fig_bar, use_container_width=True)

# 하단: 테이블 및 다운로드
st.markdown("---")
st.subheader("📋 상세 데이터 표")

# 표시할 컬럼 목록 생성 (자치구명 + 선택된 지표들)
cols_to_show = ['자치구명'] + list(valid_metrics.values())
# 중복 제거
cols_to_show = list(dict.fromkeys(cols_to_show))
# 존재하는 컬럼만 선택
cols_to_show = [c for c in cols_to_show if c in gdf.columns]

df_table = gdf[cols_to_show].sort_values(by=selected_col, ascending=(sort_opt=="하위")).head(display_count)
st.dataframe(df_table, use_container_width=True, hide_index=True)

csv = gdf[cols_to_show].to_csv(index=False).encode('utf-8-sig')
st.download_button("📥 전체 데이터 다운로드 (CSV)", csv, "seoul_analysis.csv", "text/csv")

st.markdown("#### ⚙️ 참고")
st.markdown("- 데이터 파일은 `./data/` 폴더에 위치해야 합니다. (예: `지하철 위경도.CSV`, `GGD_StationInfo_M.xlsx` 등)")
st.markdown("- 만약 파일 인코딩 문제(utf-8/cp949)가 있다면 자동으로 처리됩니다.")
st.markdown("- 추가적으로 처리해드릴 작업(예: 버스 정류장 데이터 업로드/정교한 시각화)은 파일을 올려주시면 바로 통합해 드립니다.")
