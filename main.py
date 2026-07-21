import requests
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="전국 고령화 단계구분도", layout="wide")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
TARGET_YEAR = 2026


@st.cache_data(show_spinner="인구 데이터를 불러오는 중...")
def load_population():
    df = pd.read_csv(POP_URL, compression="gzip")
    return df


@st.cache_data(show_spinner="시군구 경계 데이터를 불러오는 중...")
def load_geojson():
    res = requests.get(GEO_URL)
    res.raise_for_status()
    return res.json()


@st.cache_data(show_spinner="고령화율을 계산하는 중...")
def compute_aging_ratio(df: pd.DataFrame, year: int) -> pd.DataFrame:
    yearly = df[df["연도"] == year].copy()

    # 동 단위 '코드'의 앞 5자리 = 시군구 코드
    yearly["시군구코드"] = yearly["코드"].astype(str).str[:5]

    # '계_'로 시작하는 모든 나이 열 = 전체 인구
    total_cols = [c for c in yearly.columns if c.startswith("계_")]

    # 65세 이상 나이 열만 추출 ('계_65세' ~ '계_100세 이상')
    def age_from_col(col: str):
        age_str = col.replace("계_", "").replace("세 이상", "").replace("세", "")
        try:
            return int(age_str)
        except ValueError:
            return None

    old_cols = [c for c in total_cols if (age_from_col(c) is not None and age_from_col(c) >= 65)]

    total_sum = yearly.groupby("시군구코드")[total_cols].sum().sum(axis=1)
    old_sum = yearly.groupby("시군구코드")[old_cols].sum().sum(axis=1)

    result = pd.DataFrame({
        "총인구": total_sum,
        "고령인구": old_sum,
    })
    result["고령화율"] = (result["고령인구"] / result["총인구"] * 100).round(2)
    result = result.reset_index()  # 시군구코드 컬럼 복원
    return result


def main():
    st.title("전국 고령화 단계구분도")
    st.caption(f"{TARGET_YEAR}년 6월 기준, 시군구별 65세 이상 인구 비율")

    pop_df = load_population()
    geojson = load_geojson()
    ratio_df = compute_aging_ratio(pop_df, TARGET_YEAR)

    # geojson 속성에서 시군구명·시도명 매핑 (코드 기준, 문자열로 통일)
    code_to_name = {}
    for feature in geojson["features"]:
        props = feature["properties"]
        code_to_name[str(props["코드"])] = {
            "시군구": props["시군구"],
            "시도": props["시도"],
        }

    ratio_df["시군구코드"] = ratio_df["시군구코드"].astype(str)
    ratio_df["시군구"] = ratio_df["시군구코드"].map(lambda c: code_to_name.get(c, {}).get("시군구", ""))
    ratio_df["시도"] = ratio_df["시군구코드"].map(lambda c: code_to_name.get(c, {}).get("시도", ""))

    fig = px.choropleth(
        ratio_df,
        geojson=geojson,
        locations="시군구코드",
        featureidkey="properties.코드",
        color="고령화율",
        color_continuous_scale="Reds",
        hover_name="시군구",
        hover_data={"고령화율": ":.2f", "시군구코드": False},
        labels={"고령화율": "65세 이상 비율(%)"},
    )
    fig.update_geos(
        visible=False,      # 배경 지도(타일) 숨김, 경계만 표시
        fitbounds="locations",
    )
    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=750,
        coloraxis_colorbar=dict(title="고령화율(%)"),
    )

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("데이터 표 보기"):
        st.dataframe(
            ratio_df[["시도", "시군구", "시군구코드", "총인구", "고령인구", "고령화율"]]
            .sort_values("고령화율", ascending=False)
            .reset_index(drop=True)
        )


if __name__ == "__main__":
    main()
