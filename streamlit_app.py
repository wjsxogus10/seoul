# ... (상주 인구 파일 체크 로직 끝) ...

if df_pop is not None and df_biz is not None:
    st.success("👍 인구 및 상권 데이터는 안정적입니다.")
else:
    st.error("🚨 인구/상권 파일 중 하나에서 실행이 중단되었습니다.")
    st.stop() # <--- 여기서 앱이 멈추도록 합니다.

# [이 아래의 모든 코드는 잠시 무시됩니다.]
# st.subheader("2. 버스/지하철 밀도 파일 점검")
# ... 등등...
