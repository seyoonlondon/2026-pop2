import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import plotly.express as px

# ----------------------------------------------------
# 페이지 기본 설정
# ----------------------------------------------------
st.set_page_config(
    page_title="글로벌 보건의료 & 상급종합병원 대시보드",
    page_icon="🏥",
    layout="wide"
)

# ----------------------------------------------------
# 사이드바 메뉴 구성
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
# 페이지 2: 전세계 국가별 의료비 & UHC 지수 분석 (속도 최적화 버전)
# ----------------------------------------------------
elif page == "2. 글로벌 의료비 vs UHC 서비스 보장지수":
    st.title("📊 전 세계 국가별 1인당 의료비 & UHC 서비스 보장지수")
    st.caption("World Bank API를 통해 최신 국가별 보건의료 데이터를 실시간 수집 및 비교합니다.")

    # 경량화된 World Bank API 수집 함수 (mrv=1 파라미터로 최신 1개 연도만 조회)
    @st.cache_data(ttl=86400, show_spinner=False) # 24시간 캐시 유지
    def fetch_worldbank_data_fast(indicator_code):
        # mrv=1 : Most Recent Value 1개만 받아오므로 속도가 훨씬 빠름
        url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}?mrv=1&per_page=500&format=json"
        
        try:
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                return None
            
            data = res.json()
            if len(data) < 2 or not data[1]:
                return None

            records = []
            for entry in data[1]:
                value = entry.get("value")
                country_name = entry.get("country", {}).get("value")
                country_id = entry.get("countryiso3code")
                year = entry.get("date")
                
                # ISO 3자리 국가코드 항목만 추출 (지역/그룹 제외)
                if value is not None and country_id and len(country_id) == 3:
                    records.append({
                        "country": country_name,
                        "code": country_id,
                        "year": year,
                        "value": value
                    })

            return pd.DataFrame(records)
        except Exception:
            return None

    with st.spinner("🚀 최신 보건의료 데이터를 빠르게 불러오는 중입니다..."):
        # 1인당 의료비 지출 (USD): SH.XPD.CHEX.PC.CD
        df_health_exp = fetch_worldbank_data_fast("SH.XPD.CHEX.PC.CD")
        # UHC 보장지수 (0~100): SH_UHC_SCI
        df_uhc = fetch_worldbank_data_fast("SH_UHC_SCI")

    if df_health_exp is not None and df_uhc is not None and not df_health_exp.empty and not df_uhc.empty:
        # 데이터 병합
        df_merged = pd.merge(
            df_health_exp[["code", "country", "value", "year"]].rename(columns={"value": "health_exp_usd", "year": "exp_year"}),
            df_uhc[["code", "value", "year"]].rename(columns={"value": "uhc_index", "year": "uhc_year"}),
            on="code",
            how="inner"
        )

        st.subheader("📈 1인당 의료비 지출 대 UHC 서비스 보장지수 관계")
        
        fig = px.scatter(
            df_merged,
            x="health_exp_usd",
            y="uhc_index",
            hover_name="country",
            hover_data=["exp_year", "uhc_year"],
            log_x=True, # 로그 스케일 적용
            labels={
                "health_exp_usd": "1인당 연간 의료비 지출액 (USD, 로그 스케일)",
                "uhc_index": "UHC 서비스 보장지수 (0~100)"
            },
            title="국가별 1인당 의료비 지출 vs UHC 서비스 보장지수",
            color="uhc_index",
            color_continuous_scale="Viridis",
            height=600
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📋 국가별 상세 데이터 보기"):
            st.dataframe(
                df_merged[["country", "code", "health_exp_usd", "exp_year", "uhc_index", "uhc_year"]].sort_values(by="uhc_index", ascending=False),
                use_container_width=True
            )
    else:
        st.error("데이터를 불러오는 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

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
