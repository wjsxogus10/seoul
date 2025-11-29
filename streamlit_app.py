import streamlit as st
import pandas as pd
import os

# --------------------------------------------------------------------------
# 1. 페이지 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="🚨 최종 파일 무결성 진단")
st.title("🛠️ 최종 오류 발생 파일 진단 모드")
st.warning("이 화면에 오류가 발생하면, 해당 파일이 문제의 원인입니다.")
st.markdown("---")

# --------------------------------------------------------------------------
# 2. 파일 로드 무결성 테스트 (가장 불안정한 파일 순서로 테스트)
# --------------------------------------------------------------------------

def safe_read_and_check(file_path):
    """파일을 읽고, 컬럼 목록을 반환하며, 실패 시 에러를 띄웁니다."""
    file_name = os.path.basename(file_path)
    if not os.path.exists(file_path):
        st.error(f"❌ FATAL ERROR: [파일 없음] {file_name}")
        return None
    
    try:
        if file_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path)
            read_method = "Excel"
        else:
            try:
                df = pd.read_csv(file_path, encoding='utf-8')
                read_method = "CSV (UTF-8)"
            except:
                df = pd.read_csv(file_path, encoding='cp949')
                read_method = "CSV (CP949)"

        # 데이터가 비어있거나 컬럼이 없는지 확인
        if df.empty or len(df.columns) < 2:
            st.error(f"❌ FATAL ERROR: [데이터 비어있음] {file_name} (데이터가 비어있거나 손상됨)")
            return None
            
        st.success(f"✅ 로드 성공 ({read_method}): {file_name}")
        return df
        
    except Exception as e:
        st.error(f"❌ FATAL ERROR: [읽기 오류] {file_name} ({e})")
        return None

# --- 진단 실행 ---

st.subheader("1. 인구/상권 데이터 점검")
pop_file = './data/서울시 상권분석서비스(상주인구-자치구).csv'
biz_file = './data/서울시 상권분석서비스(집객시설-자치구).csv'

df_pop = safe_read_and_check(pop_file)
df_biz = safe_read_and_check(biz_file)

if df_pop is not None and df_biz is not None:
    st.success("👍 인구 및 상권 데이터는 안정적입니다.")
else:
    st.error("🚨 인구/상권 파일 중 하나에서 실행이 중단되었습니다.")
    st.stop() # 여기서 멈춰서 정확한 실패 지점을 찾습니다.


st.subheader("2. 버스/지하철 밀도 파일 점검")
bus_file = './data/GGD_StationInfo_M.xlsx'
subway_dens_file = './data/지하철 밀도.CSV'

df_bus = safe_read_and_check(bus_file)
df_sub_dens = safe_read_and_check(subway_dens_file)

if df_bus is not None and df_sub_dens is not None:
    st.success("👍 교통 데이터는 안정적입니다. (Bus/Subway)")
else:
    st.error("🚨 버스/지하철 파일 중 하나에서 실행이 중단되었습니다.")
    st.stop() # 여기서 멈춥니다.


st.subheader("3. 좌표 파일 점검 (부가 정보)")
coord_file = './data/지하철 위경도.CSV'
safe_read_and_check(coord_file)

st.subheader("🎉 최종 진단 완료")
st.info("이제 모든 파일은 로드 가능한 상태입니다. 다음 단계는 최종 코드 복구입니다.")
