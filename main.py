import datetime
import requests
import pandas as pd
import pytz
import streamlit as st

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 기본 안내
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="어제 박스오피스 순위",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제 일별 박스오피스 대시보드")
st.caption("영화진흥위원회(KOBIS) API를 활용한 스트림릿 박스오피스 대시보드")

# -----------------------------------------------------------------------------
# 2. 날짜 및 API 인증키 설정
# -----------------------------------------------------------------------------
# 배포 서버의 시간대가 달라도 정확히 한국 시간(KST) 기준으로 '어제' 날짜를 계산합니다.
kst = pytz.timezone('Asia/Seoul')
now_kst = datetime.datetime.now(kst)
yesterday = now_kst - datetime.timedelta(days=1)
target_dt = yesterday.strftime('%Y%m%d')

# 스트림릿 secrets 영역에서 KOBIS_KEY 추출
api_key = st.secrets.get("KOBIS_KEY")

# 인증키가 없을 경우 처리
if not api_key:
    st.error("🔑 API 인증키(KOBIS_KEY)가 설정되지 않았습니다.")
    st.info("""
    **확인 방법:**
    1. 로컬 실행 시: 프로젝트 폴더 내 `.streamlit/secrets.toml` 파일에 `KOBIS_KEY = "발급받은키"`를 등록했는지 확인하세요.
    2. Streamlit Cloud 배포 시: 앱 설정의 **Secrets** 항목에 `KOBIS_KEY = "발급받은키"`를 추가했는지 확인하세요.
    """)
    st.stop()

# -----------------------------------------------------------------------------
# 3. API 데이터 호출 및 캐싱 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_box_office_data(key: str, date_str: str):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": key,
        "targetDt": date_str
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청에 실패했습니다: {e}"

# 데이터 불러오기 실행
data, error_msg = fetch_box_office_data(api_key, target_dt)

# -----------------------------------------------------------------------------
# 4. 예외 및 오류 처리
# -----------------------------------------------------------------------------
if error_msg:
    st.error("🚨 데이터를 불러오는 중 오류가 발생했습니다.")
    st.warning(error_msg)
    st.info("💡 인터넷 연결 상태를 확인하시거나 KOBIS API 서버 상태를 확인해 주세요.")
    st.stop()

if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error("🚨 KOBIS API 오류가 발생했습니다.")
    st.warning(f"오류 메시지: {fault.get('message', '알 수 없는 오류')}")
    st.info("""
    **확인해야 할 사항:**
    1. 발급받은 KOBIS API 인증키가 올바른지 확인해 주세요.
    2. API 키의 일일 사용량이 초과되었는지 확인해 주세요.
    """)
    st.stop()

box_office_result = data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning(f"⚠️ {yesterday.strftime('%Y년 %m월 %d일')} 데이터가 존재하지 않거나 집계 중입니다.")
    st.info("""
    **확인해야 할 사항:**
    1. 영화진흥위원회(KOBIS)의 일일 데이터 집계 마감 전일 수 있습니다.
    2. 조회된 날짜에 상영 데이터가 없을 수 있으니 잠시 후 다시 시도해 주세요.
    """)
    st.stop()

# -----------------------------------------------------------------------------
# 5. 데이터 가공 및 정제
# -----------------------------------------------------------------------------
df = pd.DataFrame(daily_list)

# 문자열로 들어오는 숫자 데이터 항목들을 정수(int) 타입으로 변환
numeric_columns = ['rank', 'audiCnt', 'audiAcc', 'scrnCnt', 'showCnt', 'rankInten']
for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

# -----------------------------------------------------------------------------
# 6. 대시보드 화면 구성
# -----------------------------------------------------------------------------
st.subheader(f"📅 기준일자: {yesterday.strftime('%Y-%m-%d')} (어제)")

# [상단 & 중단] 관객수 기준 1위 및 상위 5개 추출용 (관객수 내림차순 정렬)
df_by_audi = df.sort_values(by='audiCnt', ascending=False)

top_1 = df_by_audi.iloc[0]

st.markdown(f"### 🏆 1위: **{top_1['movieNm']}**")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="당일 관객수",
        value=f"{top_1['audiCnt']:,} 명",
        delta=f"전일 대비 {top_1['rankInten']} 위" if top_1['rankInten'] != 0 else "순위 변동 없음"
    )

with col2:
    st.metric(
        label="누적 관객수",
        value=f"{top_1['audiAcc']:,} 명"
    )

with col3:
    st.metric(
        label="스크린수",
        value=f"{top_1['scrnCnt']:,} 개"
    )

st.divider()

# [중단] 관객수 상위 5편 막대그래프
st.subheader("📊 관객수 상위 5개 영화")
top_5_df = df_by_audi.head(5)

st.bar_chart(
    data=top_5_df,
    x="movieNm",
    y="audiCnt",
    use_container_width=True
)

st.divider()

# [하단] 전체 순위 표 (순위(rank) 오름차순 정렬)
st.subheader("📋 전체 박스오피스 순위")

# 순위(rank) 오름차순으로 정렬
df_by_rank = df.sort_values(by='rank', ascending=True)

display_df = df_by_rank[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
display_df.columns = ['순위', '영화명', '개봉일', '관객수', '누적관객수', '스크린수']

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "관객수": st.column_config.NumberColumn(format="%d 명"),
        "누적관객수": st.column_config.NumberColumn(format="%d 명"),
        "스크린수": st.column_config.NumberColumn(format="%d 개")
    }
)
