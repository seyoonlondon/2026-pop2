import time
import requests
import pandas as pd
import plotly.express as px
import streamlit as st
import folium
from streamlit_folium import st_folium

# ----------------------------------------------------
# 1. 페이지 및 기본 설정
# ----------------------------------------------------
st.set_page_config(
    page_title="글로벌 보건의료 & 상급종합병원 대시보드",
    page_icon="🏥",
    layout="wide"
)

WB_BASE = "https://api.worldbank.org/v2"

# 세계은행 지표 코드
IND_EXPENDITURE = "SH.XPD.CHEX.PC.CD"  # 1인당 경상 의료비 지출 (현재 US$)
IND_UHC_INDEX = "SH_UHC_SCI"           # UHC 서비스 보장지수 (0~100)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# World Bank API 안전 호출 함수
def _wb_get(path: str, params: dict, max_retries: int = 3, timeout: int = 20) -> dict:
    call_params = {**params, "format": "json"}
    last_err = None
    for attempt in range(max_retries):
        try:
            res = requests.get(
                f"{WB_BASE}{path}", params=call_params, headers=HEADERS, timeout=timeout
            )
            res.raise_for_status()
            body = res.json()
            if isinstance(body, list) and body and isinstance(body[0], dict) and "message" in body[0]:
                msg = body[0]["message"][0].get("value", str(body[0]["message"]))
                raise RuntimeError(f"World Bank API 오류 응답 ({path}): {msg}")
            return body
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"World Bank API 요청 실패 ({path}): {last_err}")

# ----------------------------------------------------
# 2. 사이드바 메뉴 구성
# ----------------------------------------------------
st.sidebar.title("📌 메뉴 Navigation")
page = st.sidebar.radio(
    "페이지를 선택하세요:",
    [
        "1. UHC 보장지수 개요",
        "2. 글로벌 의료비 vs UHC 서비스 보장지수",
        "3. 대한민국 상급종합병원 분포도"
    ]
)

# ----------------------------------------------------
# 페이지 1: UHC 보장지수 개요
# ----------------------------------------------------
if page == "1. UHC 보장지수 개요":
    st.title("🌐 UHC 서비스 보장지수 (UHC Service Coverage Index)")
    
    st.markdown("""
    ### 💡 UHC(보편적 건강보장) 지수란?
    **보편적 건강보장(Universal Health Coverage, UHC) 지수**는 WHO(세계보건기구)와 세계은행(World Bank)에서 공동 평가하는 핵심 보건 지표입니다. 
    국민이 경제적 어려움 없이 필수적인 고품질 보건의료 서비스를 받을 수 있는 수준을 **0점에서 100점 사이**의 점수로 산출합니다.
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("""
        #### 📊 주요 평가 영역 (4개 분야)
        1. **모성 및 아동 건강**: 임신·출산 관리, 영유아 예방접종, 가족계획 등
        2. **감염성 질환**: 결핵, HIV 치료, 기본 위생 및 식수 접근성
        3. **비감염성 질환**: 고혈압, 당뇨 관리율, 금연율
        4. **의료 역량 및 접근성**: 인구당 병상 수, 보건의료 인력 수, 필수 의약품 접근성
        """)
        
    with col2:
        st.success("""
        #### 🎯 지수의 의미와 활용
        * **100점에 가까울수록**: 국가 전반의 의료 서비스 접근성과 인프라 수준이 매우 우수함을 나타냅니다.
        * **국가 간 비교**: 의료 체계의 효율성 및 보건의료 불평등 해소 정도를 평가하는 국제적 기준이 됩니다.
        """)

# ----------------------------------------------------
# 페이지 2: 전세계 국가별 의료비 & UHC 지수 분석 (지도 차트 추가)
# ----------------------------------------------------
elif page == "2. 글로벌 의료비 vs UHC 서비스 보장지수":
    st.title("📊 전 세계 국가별 1인당 의료비 & UHC 서비스 보장지수")
    st.caption("World Bank Open Data에서 수집한 최신 지표를 지도 및 산점도로 분석합니다.")

    @st.cache_data(show_spinner="국가 목록 및 대륙 정보를 불러오는 중...")
    def load_country_list() -> pd.DataFrame:
        data = _wb_get("/country", {"per_page": 400})
        _, records = data
        rows = []
        for r in records:
            if r.get("region", {}).get("value") == "Aggregates":
                continue
            rows.append({
                "iso3": r["id"],
                "국가": r["name"],
                "대륙": r.get("region", {}).get("value", ""),
            })
        return pd.DataFrame(rows)

    @st.cache_data(show_spinner="World Bank 지표 데이터를 수집 및 정리 중...")
    def load_indicator(indicator_code: str) -> pd.DataFrame:
        data = _wb_get(f"/country/all/indicator/{indicator_code}", {"date": "1995:2026", "per_page": 20000})
        _, records = data
        rows = []
        for r in (records or []):
            if r.get("value") is None or not r.get("countryiso3code"):
                continue
            rows.append({
                "iso3": r["countryiso3code"],
                "값": r["value"],
                "연도": int(r["date"]),
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        # 가장 최근 연도 값 유지
        return df.sort_values("연도").drop_duplicates("iso3", keep="last").reset_index(drop=True)

    @st.cache_data(ttl=86400, show_spinner="데이터 세트를 구성 중입니다...")
    def build_dataset() -> pd.DataFrame:
        countries = load_country_list()
        exp = load_indicator(IND_EXPENDITURE).rename(columns={"값": "의료비", "연도": "의료비_연도"})
        uhc = load_indicator(IND_UHC_INDEX).rename(columns={"값": "의료수준", "연도": "의료수준_연도"})
        
        df = countries.merge(exp, on="iso3", how="inner")
        df = df.merge(uhc, on="iso3", how="inner")
        df = df[df["iso3"].str.len() == 3]
        return df.reset_index(drop=True)

    try:
        df = build_dataset()
        
        # 🗺️ 1. 전 세계 지도 차트 (Choropleth Map)
        st.subheader("🗺️ 전 세계 UHC 서비스 보장지수 지도")
        st.caption("색상이 진할수록 보편적 건강보장(UHC) 수준이 높은 국가입니다. 마우스를 올리면 상세 정보를 확인할 수 있습니다.")
        
        fig_map = px.choropleth(
            df,
            locations="iso3",
            color="의료수준",
            hover_name="국가",
            hover_data={
                "iso3": False,
                "의료수준": ":.1f점",
                "의료비": ":$,.0f",
                "의료수준_연도": True,
                "의료비_연도": True
            },
            color_continuous_scale="Viridis",
            labels={
                "의료수준": "UHC 지수 (0~100)",
                "의료비": "1인당 의료비 (USD)",
                "의료수준_연도": "UHC 조사연도",
                "의료비_연도": "의료비 조사연도"
            },
            projection="natural earth",
            height=550
        )
        fig_map.update_geos(showframe=False, showcoastlines=True, coastlinecolor="gray")
        fig_map.update_layout(margin={"r":0,"t":10,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)

        st.markdown("---")

        # 📈 2. 의료비 대비 UHC 상관관계 산점도
        st.subheader("📈 1인당 의료비 지출 대 UHC 서비스 보장지수 관계")
        st.caption("가로축: 1인당 의료비(로그 스케일) · 세로축: UHC 보장지수(0~100) · 색상: 대륙")
        
        fig_scatter = px.scatter(
            df,
            x="의료비",
            y="의료수준",
            color="대륙",
            hover_name="국가",
            hover_data=["의료비_연도", "의료수준_연도"],
            log_x=True,
            labels={"의료비": "1인당 의료비 (USD, log)", "의료수준": "UHC 보장지수 (0~100)"},
            height=550
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        # 📋 3. 상세 데이터 표
        with st.expander("📋 국가별 상세 데이터 표 보기"):
            st.dataframe(
                df[["국가", "대륙", "의료비", "의료비_연도", "의료수준", "의료수준_연도"]]
                .sort_values("의료수준", ascending=False)
                .reset_index(drop=True),
                use_container_width=True
            )

    except Exception as e:
        st.error(f"World Bank API 접속 중 오류가 발생했습니다.\n\n상세 내용: {e}")

# ----------------------------------------------------
# 페이지 3: 대한민국 상급종합병원 분포도
# ----------------------------------------------------
elif page == "3. 대한민국 상급종합병원 분포도":
    st.title("🏥 대한민국 제5기 상급종합병원 분포도 (47개소)")
    st.caption("보건복지부 지정 제5기(2024년~2026년) 상급종합병원 현황입니다.")
    
    hospitals_data = [
        # 서울권 (14개)
        {"name": "강북삼성병원", "region": "서울", "lat": 37.5685, "lon": 126.9675},
        {"name": "건국대학교병원", "region": "서울", "lat": 37.5408, "lon": 127.0718},
        {"name": "경희대학교병원", "region": "서울", "lat": 37.5938, "lon": 127.0518},
        {"name": "고려대 구로병원", "region": "서울", "lat": 37.4927, "lon": 126.8847},
        {"name": "고려대 안암병원", "region": "서울", "lat": 37.5872, "lon": 127.0264},
        {"name": "삼성서울병원", "region": "서울", "lat": 37.4882, "lon": 127.0858},
        {"name": "서울대학교병원", "region": "서울", "lat": 37.5796, "lon": 126.9990},
        {"name": "서울아산병원", "region": "서울", "lat": 37.5250, "lon": 127.1082},
        {"name": "가톨릭대 서울성모병원", "region": "서울", "lat": 37.5023, "lon": 127.0048},
        {"name": "세브란스병원", "region": "서울", "lat": 37.5624, "lon": 126.9408},
        {"name": "강남세브란스병원", "region": "서울", "lat": 37.4928, "lon": 127.0463},
        {"name": "이화대 목동병원", "region": "서울", "lat": 37.5367, "lon": 126.8863},
        {"name": "중앙대학교병원", "region": "서울", "lat": 37.5065, "lon": 126.9602},
        {"name": "한양대학교병원", "region": "서울", "lat": 37.5592, "lon": 127.0439},

        # 경기서북부 (4개)
        {"name": "가천대 길병원", "region": "경기서북", "lat": 37.4520, "lon": 126.7086},
        {"name": "인하대학교병원", "region": "경기서북", "lat": 37.4589, "lon": 126.6338},
        {"name": "가톨릭대 인천성모병원", "region": "경기서북", "lat": 37.4845, "lon": 126.7248},
        {"name": "순천향대 부천병원", "region": "경기서북", "lat": 37.5042, "lon": 126.7630},

        # 경기남부 (5개)
        {"name": "가톨릭대 성빈센트병원", "region": "경기남부", "lat": 37.2777, "lon": 127.0284},
        {"name": "고려대 안산병원", "region": "경기남부", "lat": 37.3184, "lon": 126.8258},
        {"name": "분당서울대학교병원", "region": "경기남부", "lat": 37.3518, "lon": 127.1232},
        {"name": "아주대학교병원", "region": "경기남부", "lat": 37.2794, "lon": 127.0478},
        {"name": "한림대 성심병원", "region": "경기남부", "lat": 37.3900, "lon": 126.9634},

        # 강원 (2개)
        {"name": "강릉아산병원", "region": "강원", "lat": 37.8188, "lon": 128.8576},
        {"name": "연세대 원주세브란스기독병원", "region": "강원", "lat": 37.3486, "lon": 127.9463},

        # 충북 (1개)
        {"name": "충북대학교병원", "region": "충북", "lat": 36.6241, "lon": 127.4608},

        # 충남 (3개)
        {"name": "건양대학교병원", "region": "충남", "lat": 36.3061, "lon": 127.3428},
        {"name": "단국대 부속병원", "region": "충남", "lat": 36.8407, "lon": 127.1728},
        {"name": "충남대학교병원", "region": "충남", "lat": 36.3170, "lon": 127.4158},

        # 전북 (2개)
        {"name": "원광대학교병원", "region": "전북", "lat": 35.9667, "lon": 126.9583},
        {"name": "전북대학교병원", "region": "전북", "lat": 35.8475, "lon": 127.1415},

        # 전남 (3개)
        {"name": "전남대학교병원", "region": "전남", "lat": 35.1413, "lon": 126.9221},
        {"name": "조선대학교병원", "region": "전남", "lat": 35.1404, "lon": 126.9298},
        {"name": "화순전남대학교병원", "region": "전남", "lat": 35.0592, "lon": 126.9882},

        # 경북 (5개)
        {"name": "경북대학교병원", "region": "경북", "lat": 35.8662, "lon": 128.6042},
        {"name": "계명대 동산병원", "region": "경북", "lat": 35.8540, "lon": 128.4812},
        {"name": "대구가톨릭대학교병원", "region": "경북", "lat": 35.8436, "lon": 128.5678},
        {"name": "영남대학교병원", "region": "경북", "lat": 35.8475, "lon": 128.5978},
        {"name": "칠곡경북대학교병원", "region": "경북", "lat": 35.9555, "lon": 128.5639},

        # 경남동부 (6개)
        {"name": "고신대 복음병원", "region": "경남동부", "lat": 35.0772, "lon": 129.0175},
        {"name": "동아대학교병원", "region": "경남동부", "lat": 35.1189, "lon": 129.0182},
        {"name": "부산대학교병원", "region": "경남동부", "lat": 35.1010, "lon": 129.0189},
        {"name": "양산부산대학교병원", "region": "경남동부", "lat": 35.3283, "lon": 129.0083},
        {"name": "인제대 부산백병원", "region": "경남동부", "lat": 35.1481, "lon": 129.0225},
        {"name": "울산대학교병원", "region": "경남동부", "lat": 35.5233, "lon": 129.4283},

        # 경남서부 (2개)
        {"name": "경상국립대학교병원", "region": "경남서부", "lat": 35.1757, "lon": 128.0955},
        {"name": "성균관대 삼성창원병원", "region": "경남서부", "lat": 35.2403, "lon": 128.5833},
    ]

    df = pd.DataFrame(hospitals_data)

    col_filter, col_metric = st.columns([2, 1])
    
    with col_filter:
        region_list = ["전체"] + list(df["region"].unique())
        selected_region = st.selectbox("진료권역 선택:", region_list)

    if selected_region != "전체":
        filtered_df = df[df["region"] == selected_region]
    else:
        filtered_df = df

    with col_metric:
        st.metric("해당 권역 병원 수", f"{len(filtered_df)}개소")

    m = folium.Map(location=[36.3, 127.8], zoom_start=7, tiles="cartodbpositron")

    for _, row in filtered_df.iterrows():
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(f"<b>{row['name']}</b><br>권역: {row['region']}", max_width=200),
            tooltip=row["name"],
            icon=folium.Icon(color="red", icon="hospital-o", prefix="fa")
        ).add_to(m)

    st_folium(m, width="100%", height=550)

    with st.expander("📋 선택된 권역 병원 목록 확인하기"):
        st.dataframe(filtered_df[["name", "region"]], use_container_width=True)
