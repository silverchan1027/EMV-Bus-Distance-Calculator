import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

BMS_CRS = "EPSG:5181"


def _normalize_id(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def make_stop_geodataframe(stop_df: pd.DataFrame, target_crs) -> gpd.GeoDataFrame:
    valid_stops = stop_df.copy()
    valid_stops["X좌표"] = pd.to_numeric(valid_stops["X좌표"], errors="coerce")
    valid_stops["Y좌표"] = pd.to_numeric(valid_stops["Y좌표"], errors="coerce")
    valid_stops = valid_stops.dropna(subset=["X좌표", "Y좌표"]).copy()
    if valid_stops.empty:
        return gpd.GeoDataFrame()
    stop_gdf = gpd.GeoDataFrame(
        valid_stops,
        geometry=gpd.points_from_xy(valid_stops["Y좌표"], valid_stops["X좌표"]),
        crs=BMS_CRS,
    )
    stop_gdf = stop_gdf.to_crs(target_crs)
    stop_gdf["KTDB_X"] = stop_gdf.geometry.x
    stop_gdf["KTDB_Y"] = stop_gdf.geometry.y
    return stop_gdf


def find_nearest_link(stop_df: pd.DataFrame, link_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    print()
    print("=" * 150)
    print("정류장별 가장 가까운 KTDB LINK")
    print("=" * 150)

    if link_gdf.empty:
        raise ValueError("KTDB LINK 데이터가 비어 있습니다.")
    if link_gdf.crs is None:
        raise ValueError("KTDB LINK의 좌표계 정보가 없습니다.")

    stop_gdf = make_stop_geodataframe(stop_df, link_gdf.crs)
    if stop_gdf.empty:
        print("좌표가 있는 정류장이 없습니다.")
        return pd.DataFrame()

    required_columns = [
        "LINK_ID", "F_NODE", "T_NODE", "LENGTH", "ROAD_NAME",
        "ROAD_TYPE", "ROAD_USE", "geometry",
    ]
    missing_columns = [c for c in required_columns if c not in link_gdf.columns]
    if missing_columns:
        raise KeyError(f"KTDB LINK 데이터에 필요한 컬럼이 없습니다: {missing_columns}")

    valid_links = (
        link_gdf[required_columns]
        .dropna(subset=["LINK_ID", "F_NODE", "T_NODE", "geometry"])
        .copy()
    )
    valid_links["LINK_GEOMETRY"] = valid_links.geometry

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
        nearest.sort_values(["정류장순서", "링크매칭거리_m"])
        .drop_duplicates(subset=["정류장순서", "정류장아이디"], keep="first")
        .reset_index(drop=True)
    )
    nearest["LENGTH"] = pd.to_numeric(nearest["LENGTH"], errors="coerce")
    nearest["링크매칭거리_m"] = pd.to_numeric(
        nearest["링크매칭거리_m"], errors="coerce"
    ).round(2)

    result_columns = [
        "정류장순서", "정류장아이디", "정류장명", "X좌표", "Y좌표",
        "KTDB_X", "KTDB_Y", "LINK_ID", "F_NODE", "T_NODE", "LENGTH",
        "ROAD_NAME", "ROAD_TYPE", "ROAD_USE", "링크매칭거리_m", "LINK_GEOMETRY",
    ]
    result = nearest[result_columns].copy()

    display_columns = [
        "정류장순서", "정류장아이디", "정류장명", "KTDB_X", "KTDB_Y",
        "LINK_ID", "F_NODE", "T_NODE", "LENGTH", "ROAD_NAME", "링크매칭거리_m",
    ]
    print(result[display_columns].to_string(index=False))
    print("=" * 150)
    return result


def assign_link_projection(nearest_link_df: pd.DataFrame) -> pd.DataFrame:
    """
    정류장 좌표를 최근접 KTDB Link 위의 가장 가까운 지점으로 투영한다.

    결과 컬럼:
    - 투영점_X / 투영점_Y
    - F_NODE방향_부분거리_m
    - T_NODE방향_부분거리_m
    - 투영오차_m
    """

    print()
    print("=" * 170)
    print("정류장별 LINK 내부 투영 결과")
    print("=" * 170)

    if nearest_link_df.empty:
        raise ValueError("최근접 LINK 결과가 비어 있습니다.")

    required_columns = [
        "KTDB_X", "KTDB_Y", "LINK_ID", "F_NODE", "T_NODE",
        "LENGTH", "LINK_GEOMETRY",
    ]
    missing_columns = [c for c in required_columns if c not in nearest_link_df.columns]
    if missing_columns:
        raise KeyError(f"LINK 투영 계산에 필요한 컬럼이 없습니다: {missing_columns}")

    result = nearest_link_df.copy()
    projection_rows = []

    for _, row in result.iterrows():
        link_geometry = row["LINK_GEOMETRY"]
        stop_point = Point(float(row["KTDB_X"]), float(row["KTDB_Y"]))

        if link_geometry is None or link_geometry.is_empty:
            raise ValueError(f"LINK geometry가 비어 있습니다: {row['LINK_ID']}")

        geometry_length = float(link_geometry.length)
        attribute_length = pd.to_numeric(row["LENGTH"], errors="coerce")
        if geometry_length <= 0:
            raise ValueError(f"LINK geometry 길이가 0 이하입니다: {row['LINK_ID']}")

        projected_geometry_distance = float(link_geometry.project(stop_point))
        projected_point = link_geometry.interpolate(projected_geometry_distance)
        projection_ratio = projected_geometry_distance / geometry_length

        if pd.isna(attribute_length) or attribute_length <= 0:
            effective_link_length = geometry_length
        else:
            effective_link_length = float(attribute_length)

        from_distance = effective_link_length * projection_ratio
        to_distance = effective_link_length - from_distance

        projection_rows.append({
            "투영점_X": projected_point.x,
            "투영점_Y": projected_point.y,
            "투영점_비율": projection_ratio,
            "LINK_GEOMETRY길이_m": geometry_length,
            "유효_LINK길이_m": effective_link_length,
            "F_NODE방향_부분거리_m": from_distance,
            "T_NODE방향_부분거리_m": to_distance,
            "투영오차_m": stop_point.distance(projected_point),
        })

    projection_df = pd.DataFrame(projection_rows, index=result.index)
    result = pd.concat([result, projection_df], axis=1)

    for column in [
        "투영점_X", "투영점_Y", "LINK_GEOMETRY길이_m", "유효_LINK길이_m",
        "F_NODE방향_부분거리_m", "T_NODE방향_부분거리_m", "투영오차_m",
    ]:
        result[column] = result[column].round(2)
    result["투영점_비율"] = result["투영점_비율"].round(6)

    display_columns = [
        "정류장순서", "정류장명", "LINK_ID", "F_NODE", "T_NODE",
        "유효_LINK길이_m", "투영점_비율", "F_NODE방향_부분거리_m",
        "T_NODE방향_부분거리_m", "투영오차_m",
    ]
    print(result[display_columns].to_string(index=False))
    print("=" * 170)
    return result


def assign_representative_node(
    nearest_link_df: pd.DataFrame,
    node_gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """기존 대표 Node 방식과 비교하기 위해 유지한다."""

    print()
    print("=" * 150)
    print("정류장별 대표 NODE 선택 결과")
    print("=" * 150)

    if nearest_link_df.empty:
        raise ValueError("최근접 LINK 결과가 비어 있습니다.")
    if node_gdf.empty:
        raise ValueError("KTDB NODE 데이터가 비어 있습니다.")

    required_node_columns = ["NODE_ID", "geometry"]
    missing_columns = [c for c in required_node_columns if c not in node_gdf.columns]
    if missing_columns:
        raise KeyError(f"KTDB NODE 데이터에 필요한 컬럼이 없습니다: {missing_columns}")

    result = nearest_link_df.copy()
    result["F_NODE_KEY"] = result["F_NODE"].map(_normalize_id)
    result["T_NODE_KEY"] = result["T_NODE"].map(_normalize_id)

    node_lookup = node_gdf[["NODE_ID", "geometry"]].copy()
    node_lookup["NODE_KEY"] = node_lookup["NODE_ID"].map(_normalize_id)
    node_lookup["NODE_X"] = node_lookup.geometry.x
    node_lookup["NODE_Y"] = node_lookup.geometry.y

    node_xy = node_lookup[["NODE_KEY", "NODE_X", "NODE_Y"]].drop_duplicates(
        subset=["NODE_KEY"], keep="first"
    )

    result = result.merge(
        node_xy.rename(columns={
            "NODE_KEY": "F_NODE_KEY", "NODE_X": "F_NODE_X", "NODE_Y": "F_NODE_Y"
        }),
        on="F_NODE_KEY",
        how="left",
    )
    result = result.merge(
        node_xy.rename(columns={
            "NODE_KEY": "T_NODE_KEY", "NODE_X": "T_NODE_X", "NODE_Y": "T_NODE_Y"
        }),
        on="T_NODE_KEY",
        how="left",
    )

    missing_node_rows = result[
        result[["F_NODE_X", "F_NODE_Y", "T_NODE_X", "T_NODE_Y"]].isna().any(axis=1)
    ]
    if not missing_node_rows.empty:
        missing_ids = missing_node_rows[["F_NODE", "T_NODE"]].to_dict("records")
        raise ValueError(
            "F_NODE 또는 T_NODE 좌표를 KTDB NODE에서 찾지 못했습니다: "
            f"{missing_ids}"
        )

    result["F_NODE거리_m"] = (
        (result["KTDB_X"] - result["F_NODE_X"]) ** 2
        + (result["KTDB_Y"] - result["F_NODE_Y"]) ** 2
    ) ** 0.5
    result["T_NODE거리_m"] = (
        (result["KTDB_X"] - result["T_NODE_X"]) ** 2
        + (result["KTDB_Y"] - result["T_NODE_Y"]) ** 2
    ) ** 0.5

    t_is_closer = result["T_NODE거리_m"] < result["F_NODE거리_m"]
    result["대표_NODE_구분"] = "F_NODE"
    result.loc[t_is_closer, "대표_NODE_구분"] = "T_NODE"
    result["대표_NODE"] = result["F_NODE"]
    result.loc[t_is_closer, "대표_NODE"] = result.loc[t_is_closer, "T_NODE"]
    result["대표_NODE거리_m"] = result[["F_NODE거리_m", "T_NODE거리_m"]].min(axis=1)

    for column in ["F_NODE거리_m", "T_NODE거리_m", "대표_NODE거리_m"]:
        result[column] = result[column].round(2)

    display_columns = [
        "정류장순서", "정류장명", "LINK_ID", "F_NODE", "F_NODE거리_m",
        "T_NODE", "T_NODE거리_m", "대표_NODE", "대표_NODE_구분", "대표_NODE거리_m",
    ]
    print(result[display_columns].to_string(index=False))
    print("=" * 150)
    return result.drop(columns=["F_NODE_KEY", "T_NODE_KEY"])


def check_bms_link_ids(stop_df: pd.DataFrame, link_gdf: gpd.GeoDataFrame) -> None:
    print()
    print("=" * 100)
    print("BMS 링크아이디와 KTDB LINK_ID 일치 여부")
    print("=" * 100)

    ktdb_link_ids = set(link_gdf["LINK_ID"].dropna().map(_normalize_id))

    for _, stop in stop_df.iterrows():
        bms_link_id = _normalize_id(stop["링크아이디"])
        exists = bms_link_id in ktdb_link_ids
        status = "있음" if exists else "없음"
        print(
            f"{stop['정류장순서']}번 {stop['정류장명']} / "
            f"BMS 링크아이디 {bms_link_id} : {status}"
        )

    print("=" * 100)