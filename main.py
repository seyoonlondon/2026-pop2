import time

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

# 일부 API는 기본 requests User-Agent를 차단하므로 브라우저처럼 위장
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _wb_get(path: str, params: dict, max_retries: int = 3, timeout: int = 20) -> dict:
    """World Bank API 호출 + 재시도. 실패 시 명확한 에러 메시지로 변환."""
    call_params = {**params, "format": "json"}
    last_err = None
    for attempt in range(max_retries):
        try:
            res = requests.get(
                f"{WB_BASE}{path}", params=call_params, headers=HEADERS, timeout=timeout
            )
            res.raise_for_status()
            body = res.json()
            # World Bank API는 잘못된 요청도 200과 함께 message로 내려줄 때가 있음
            if isinstance(body, list) and body and isinstance(body[0], dict) and "message" in body[0]:
                msg = body[0]["message"][0].get("value", str(body[0]["message"]))
                raise RuntimeError(f"World Bank API 오류 응답 ({path}): {msg}")
            return body
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"World Bank API 요청 실패 ({path}): {last_err}")


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


@st.cache_data(show_spinner="세계은행 지표를 불러오는 중...")
def load_indicator(indicator_code: str) -> pd.DataFrame:
    """국가별 값을 최근 30년 범위로 받아온 뒤, 국가마다 가장 최근 연도 값만 남긴다."""
    data = _wb_get(
        f"/country/all/indicator/{indicator_code}",
        {"date": "1995:2026", "per_page": 20000},
    )
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
    # 국가별로 가장 최근 연도의 값만 남김
    df = df.sort_values("연도").drop_duplicates("iso3", keep="last").reset_index(drop=True)
    return df


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

    try:
        df = build_dataset()
    except RuntimeError as e:
        st.error(
            "World Bank API에서 데이터를 불러오지 못했어요. "
            "일시적인 API 장애일 수 있으니 새로고침을 눌러 다시 시도해 주세요.\n\n"
            f"오류 내용: {e}"
        )
        st.stop()

    if df.empty:
        st.error("데이터를 불러왔지만 병합 결과가 비어 있어요. API 응답 형식이 바뀌었을 수 있습니다.")
        st.stop()

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
