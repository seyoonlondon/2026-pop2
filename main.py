import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="전세계 의료비 · 의료 수준", layout="wide")

WB_BASE = "https://api.worldbank.org/v2"

# 세계은행 지표 코드
IND_EXPENDITURE = "SH.XPD.CHEX.PC.CD"   # 1인당 경상 의료비 지출 (현재 US$)
IND_UHC_INDEX = "SH.UHC.SRVS.CV.XD"     # UHC 필수서비스 보장지수 (0~100, 의료 수준 대리지표)

METRICS = {
    "평균 의료비 (1인당, US$)": {
        "code": IND_EXPENDITURE,
        "col": "의료비",
        "color_scale": "Blues",
        "hover_fmt": ":.0f",
        "unit": "US$",
    },
    "전반적 의료 수준 (UHC 보장지수, 0~100)": {
        "code": IND_UHC_INDEX,
        "col": "의료수준",
        "color_scale": "Greens",
        "hover_fmt": ":.1f",
        "unit": "점",
    },
}


@st.cache_data(show_spinner="국가 목록을 불러오는 중...")
def load_country_list() -> pd.DataFrame:
    """실제 '국가'만 추려낸다 (World, 소득그룹 등 집계 항목 제외)."""
    res = requests.get(f"{WB_BASE}/country", params={"format": "json", "per_page": 400})
    res.raise_for_status()
    _, records = res.json()
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


@st.cache_data(show_spinner="세계은행 지표를 불러오는 중...")
def load_indicator(indicator_code: str) -> pd.DataFrame:
    """국가별 가장 최근 값(mrnev=1)을 가져온다."""
    res = requests.get(
        f"{WB_BASE}/country/all/indicator/{indicator_code}",
        params={"format": "json", "per_page": 20000, "mrnev": 1},
    )
    res.raise_for_status()
    _, records = res.json()
    rows = []
    for r in records:
        if r.get("value") is None:
            continue
        rows.append({
            "iso3": r["countryiso3code"],
            "값": r["value"],
            "연도": r["date"],
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner="데이터를 정리하는 중...")
def build_dataset() -> pd.DataFrame:
    countries = load_country_list()

    exp = load_indicator(IND_EXPENDITURE).rename(columns={"값": "의료비", "연도": "의료비_연도"})
    uhc = load_indicator(IND_UHC_INDEX).rename(columns={"값": "의료수준", "연도": "의료수준_연도"})

    df = countries.merge(exp, on="iso3", how="inner")
    df = df.merge(uhc, on="iso3", how="inner")
    df = df[df["iso3"].str.len() == 3]
    return df.reset_index(drop=True)


def main():
    st.title("전세계 국가별 평균 의료비 & 의료 수준")
    st.caption("데이터 출처: World Bank Open Data (국가별로 가장 최근 발표 연도 값 사용)")

    df = build_dataset()

    metric_label = st.selectbox("지표 선택", list(METRICS.keys()))
    metric = METRICS[metric_label]
    col = metric["col"]

    fig = px.choropleth(
        df,
        locations="iso3",
        locationmode="ISO-3",
        color=col,
        color_continuous_scale=metric["color_scale"],
        hover_name="국가",
        hover_data={col: metric["hover_fmt"], "iso3": False},
        labels={col: metric_label},
    )
    fig.update_geos(
        visible=False,
        showcountries=True,
        countrycolor="lightgray",
        projection_type="natural earth",
    )
    fig.update_layout(
        margin={"r": 0, "t": 10, "l": 0, "b": 0},
        height=650,
        coloraxis_colorbar=dict(title=metric["unit"]),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("의료비 대비 의료 수준")
    st.caption("가로축: 1인당 의료비(로그 스케일) · 세로축: UHC 보장지수 · 점 색상: 대륙")
    scatter = px.scatter(
        df,
        x="의료비",
        y="의료수준",
        color="대륙",
        hover_name="국가",
        log_x=True,
        labels={"의료비": "1인당 의료비 (US$, log)", "의료수준": "UHC 보장지수"},
    )
    scatter.update_layout(height=500, margin={"r": 0, "t": 10, "l": 0, "b": 0})
    st.plotly_chart(scatter, use_container_width=True)

    with st.expander("데이터 표 보기"):
        st.dataframe(
            df[["국가", "대륙", "의료비", "의료비_연도", "의료수준", "의료수준_연도"]]
            .sort_values(col, ascending=False)
            .reset_index(drop=True)
        )


if __name__ == "__main__":
    main()
