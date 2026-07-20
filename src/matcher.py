import pandas as pd
import geopandas as gpd


# =====================================================
# BMS 정류장 좌표의 좌표계
# =====================================================
# BMS 좌표:
#   X좌표 = Northing
#   Y좌표 = Easting
BMS_CRS = "EPSG:5181"


# =====================================================
# BMS 정류장 좌표를 KTDB 좌표계로 변환
# =====================================================
def make_stop_geodataframe(
    stop_df: pd.DataFrame,
    target_crs,
) -> gpd.GeoDataFrame:

    valid_stops = stop_df.copy()

    valid_stops["X좌표"] = pd.to_numeric(
        valid_stops["X좌표"],
        errors="coerce",
    )
    valid_stops["Y좌표"] = pd.to_numeric(
        valid_stops["Y좌표"],
        errors="coerce",
    )

    valid_stops = valid_stops.dropna(
        subset=["X좌표", "Y좌표"]
    ).copy()

    if valid_stops.empty:
        return gpd.GeoDataFrame()

    stop_gdf = gpd.GeoDataFrame(
        valid_stops,
        geometry=gpd.points_from_xy(
            valid_stops["Y좌표"],
            valid_stops["X좌표"],
        ),
        crs=BMS_CRS,
    )

    stop_gdf = stop_gdf.to_crs(target_crs)

    stop_gdf["KTDB_X"] = stop_gdf.geometry.x
    stop_gdf["KTDB_Y"] = stop_gdf.geometry.y

    return stop_gdf


# =====================================================
# 정류장과 가장 가까운 KTDB LINK 찾기
# =====================================================
def find_nearest_link(
    stop_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:

    print("\n")
    print("=" * 130)
    print("정류장별 가장 가까운 KTDB LINK")
    print("=" * 130)

    if link_gdf.empty:
        raise ValueError("KTDB LINK 데이터가 비어 있습니다.")

    if link_gdf.crs is None:
        raise ValueError("KTDB LINK의 좌표계 정보가 없습니다.")

    stop_gdf = make_stop_geodataframe(
        stop_df,
        link_gdf.crs,
    )

    if stop_gdf.empty:
        print("좌표가 있는 정류장이 없습니다.")
        return pd.DataFrame()

    required_columns = [
        "LINK_ID",
        "F_NODE",
        "T_NODE",
        "LENGTH",
        "ROAD_NAME",
        "ROAD_TYPE",
        "ROAD_USE",
        "geometry",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in link_gdf.columns
    ]

    if missing_columns:
        raise KeyError(
            f"KTDB LINK 데이터에 필요한 컬럼이 없습니다: {missing_columns}"
        )

    valid_links = (
        link_gdf[required_columns]
        .dropna(
            subset=[
                "LINK_ID",
                "F_NODE",
                "T_NODE",
                "geometry",
            ]
        )
        .copy()
    )

    nearest = gpd.sjoin_nearest(
        stop_gdf,
        valid_links,
        how="left",
        distance_col="링크매칭거리_m",
    )

    if nearest.empty:
        print("최근접 KTDB LINK를 찾지 못했습니다.")
        return pd.DataFrame()

    nearest = (
        nearest
        .sort_values(
            ["정류장순서", "링크매칭거리_m"]
        )
        .drop_duplicates(
            subset=["정류장순서", "정류장아이디"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    nearest["LENGTH"] = pd.to_numeric(
        nearest["LENGTH"],
        errors="coerce",
    )

    nearest["링크매칭거리_m"] = pd.to_numeric(
        nearest["링크매칭거리_m"],
        errors="coerce",
    ).round(2)

    result = nearest[
        [
            "정류장순서",
            "정류장아이디",
            "정류장명",
            "X좌표",
            "Y좌표",
            "KTDB_X",
            "KTDB_Y",
            "LINK_ID",
            "F_NODE",
            "T_NODE",
            "LENGTH",
            "ROAD_NAME",
            "링크매칭거리_m",
        ]
    ].copy()

    print(result.to_string(index=False))
    print("=" * 130)

    return result


# =====================================================
# 정류장별 대표 NODE 선택
# =====================================================
def assign_representative_node(
    nearest_link_df: pd.DataFrame,
    node_gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """
    매칭된 LINK의 F_NODE와 T_NODE 중에서 정류장에 더 가까운 NODE를
    대표 NODE로 선택한다.
    """

    print("\n")
    print("=" * 150)
    print("정류장별 대표 NODE 선택 결과")
    print("=" * 150)

    if nearest_link_df.empty:
        raise ValueError("최근접 LINK 결과가 비어 있습니다.")

    if node_gdf.empty:
        raise ValueError("KTDB NODE 데이터가 비어 있습니다.")

    required_node_columns = ["NODE_ID", "geometry"]
    missing_columns = [
        column
        for column in required_node_columns
        if column not in node_gdf.columns
    ]

    if missing_columns:
        raise KeyError(
            f"KTDB NODE 데이터에 필요한 컬럼이 없습니다: {missing_columns}"
        )

    result = nearest_link_df.copy()

    # 문자열로 통일하여 NODE ID 자료형 차이 방지
    result["F_NODE_KEY"] = result["F_NODE"].astype(str).str.strip()
    result["T_NODE_KEY"] = result["T_NODE"].astype(str).str.strip()

    node_lookup = node_gdf[
        ["NODE_ID", "geometry"]
    ].copy()

    node_lookup["NODE_KEY"] = (
        node_lookup["NODE_ID"]
        .astype(str)
        .str.strip()
    )

    node_lookup["NODE_X"] = node_lookup.geometry.x
    node_lookup["NODE_Y"] = node_lookup.geometry.y

    node_xy = node_lookup[
        ["NODE_KEY", "NODE_X", "NODE_Y"]
    ].drop_duplicates(
        subset=["NODE_KEY"],
        keep="first",
    )

    # F_NODE 좌표 결합
    result = result.merge(
        node_xy.rename(
            columns={
                "NODE_KEY": "F_NODE_KEY",
                "NODE_X": "F_NODE_X",
                "NODE_Y": "F_NODE_Y",
            }
        ),
        on="F_NODE_KEY",
        how="left",
    )

    # T_NODE 좌표 결합
    result = result.merge(
        node_xy.rename(
            columns={
                "NODE_KEY": "T_NODE_KEY",
                "NODE_X": "T_NODE_X",
                "NODE_Y": "T_NODE_Y",
            }
        ),
        on="T_NODE_KEY",
        how="left",
    )

    # 유클리드 거리 계산: KTDB CRS 단위가 metre
    result["F_NODE거리_m"] = (
        (result["KTDB_X"] - result["F_NODE_X"]) ** 2
        + (result["KTDB_Y"] - result["F_NODE_Y"]) ** 2
    ) ** 0.5

    result["T_NODE거리_m"] = (
        (result["KTDB_X"] - result["T_NODE_X"]) ** 2
        + (result["KTDB_Y"] - result["T_NODE_Y"]) ** 2
    ) ** 0.5

    result["대표_NODE_구분"] = "F_NODE"

    t_is_closer = (
        result["T_NODE거리_m"]
        < result["F_NODE거리_m"]
    )

    result.loc[
        t_is_closer,
        "대표_NODE_구분",
    ] = "T_NODE"

    result["대표_NODE"] = result["F_NODE"]

    result.loc[
        t_is_closer,
        "대표_NODE",
    ] = result.loc[
        t_is_closer,
        "T_NODE",
    ]

    result["대표_NODE거리_m"] = result[
        ["F_NODE거리_m", "T_NODE거리_m"]
    ].min(axis=1)

    result["F_NODE거리_m"] = result[
        "F_NODE거리_m"
    ].round(2)

    result["T_NODE거리_m"] = result[
        "T_NODE거리_m"
    ].round(2)

    result["대표_NODE거리_m"] = result[
        "대표_NODE거리_m"
    ].round(2)

    # NODE 좌표를 못 찾은 경우 명확하게 중단
    missing_node_rows = result[
        result[
            [
                "F_NODE_X",
                "F_NODE_Y",
                "T_NODE_X",
                "T_NODE_Y",
            ]
        ].isna().any(axis=1)
    ]

    if not missing_node_rows.empty:
        missing_ids = missing_node_rows[
            ["F_NODE", "T_NODE"]
        ].to_dict("records")

        raise ValueError(
            "F_NODE 또는 T_NODE 좌표를 KTDB NODE에서 찾지 못했습니다: "
            f"{missing_ids}"
        )

    display_columns = [
        "정류장순서",
        "정류장명",
        "LINK_ID",
        "F_NODE",
        "F_NODE거리_m",
        "T_NODE",
        "T_NODE거리_m",
        "대표_NODE",
        "대표_NODE_구분",
        "대표_NODE거리_m",
    ]

    print(result[display_columns].to_string(index=False))
    print("=" * 150)

    return result.drop(
        columns=["F_NODE_KEY", "T_NODE_KEY"],
    )


# =====================================================
# BMS 링크아이디가 KTDB LINK_ID에 존재하는지 확인
# =====================================================
def check_bms_link_ids(
    stop_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
) -> None:

    print("\n")
    print("=" * 100)
    print("BMS 링크아이디와 KTDB LINK_ID 일치 여부")
    print("=" * 100)

    ktdb_link_ids = set(
        link_gdf["LINK_ID"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    for _, stop in stop_df.iterrows():

        bms_link_id = str(stop["링크아이디"]).strip()

        if bms_link_id.endswith(".0"):
            bms_link_id = bms_link_id[:-2]

        exists = bms_link_id in ktdb_link_ids
        status = "있음" if exists else "없음"

        print(
            f"{stop['정류장순서']}번 "
            f"{stop['정류장명']} / "
            f"BMS 링크아이디 {bms_link_id} : {status}"
        )

    print("=" * 100)
