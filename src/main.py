import pandas as pd
import geopandas as gpd

from load_data import load_bms_data, load_ktdb_data


# =====================================================
# Pandas 출력 옵션
# =====================================================
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 50)
pd.set_option("display.expand_frame_repr", False)


# =====================================================
# 테스트 조건
# =====================================================
TARGET_ROUTE_ID = 208000016
START_SEQUENCE = 68
STOP_COUNT = 3

# BMS 정류장 좌표의 좌표계
# BMS 좌표는 (Easting=Y좌표, Northing=X좌표) 형태이며
# EPSG:5181로 해석한 뒤 KTDB 좌표계로 변환한다.
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

    # BMS:
    #   X좌표 = Northing
    #   Y좌표 = Easting
    #
    # GeoPandas:
    #   points_from_xy(Easting, Northing)
    stop_gdf = gpd.GeoDataFrame(
        valid_stops,
        geometry=gpd.points_from_xy(
            valid_stops["Y좌표"],
            valid_stops["X좌표"],
        ),
        crs=BMS_CRS,
    )

    # KTDB Node-Link의 좌표계로 실제 좌표 변환
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

    if valid_links.empty:
        raise ValueError("사용 가능한 KTDB LINK 데이터가 없습니다.")

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
            [
                "정류장순서",
                "링크매칭거리_m",
            ]
        )
        .drop_duplicates(
            subset=[
                "정류장순서",
                "정류장아이디",
            ],
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


# =====================================================
# 메인 함수
# =====================================================
def main() -> None:

    print("=" * 80)
    print("국토부 Node-Link 기반 버스 정류장 거리 계산")
    print("=" * 80)

    # 1. BMS 데이터 읽기
    datasets = load_bms_data()

    route_stop_df = datasets["route_stop"]
    stop_history_df = datasets["stop_history"]

    # 2. KTDB Node-Link 읽기
    node_gdf, link_gdf = load_ktdb_data()

    print("\n========== KTDB NODE 정보 ==========")
    print(f"행 수: {len(node_gdf):,}")
    print(f"좌표계: {node_gdf.crs}")
    print(f"전체 좌표 범위: {node_gdf.total_bounds}")
    print(f"컬럼: {node_gdf.columns.tolist()}")

    print("\n========== KTDB LINK 정보 ==========")
    print(f"행 수: {len(link_gdf):,}")
    print(f"좌표계: {link_gdf.crs}")
    print(f"전체 좌표 범위: {link_gdf.total_bounds}")
    print(f"컬럼: {link_gdf.columns.tolist()}")

    # 3. 대상 노선 선택
    selected_route = (
        route_stop_df[
            route_stop_df["노선아이디"] == TARGET_ROUTE_ID
        ]
        .drop_duplicates(
            subset=["정류장순서", "정류장아이디"],
            keep="first",
        )
        .sort_values("정류장순서")
        .reset_index(drop=True)
    )

    if selected_route.empty:
        print(f"노선을 찾을 수 없습니다: {TARGET_ROUTE_ID}")
        return

    print(f"\n대상 노선아이디: {TARGET_ROUTE_ID}")
    print(f"전체 정류장 수: {len(selected_route):,}")

    print("\n========== 노선 앞부분 20개 ==========\n")

    route_preview = selected_route[
        [
            "정류장순서",
            "정류장아이디",
            "GIS거리",
            "누적거리",
            "확정거리",
        ]
    ].head(20)

    print(route_preview.to_string(index=False))

    # 4. 연속된 정류장 선택
    selected_stops = (
        selected_route[
            selected_route["정류장순서"].between(
                START_SEQUENCE,
                START_SEQUENCE + STOP_COUNT - 1,
            )
        ]
        .copy()
    )

    if len(selected_stops) != STOP_COUNT:
        print(
            f"정류장 {STOP_COUNT}개를 찾지 못했습니다. "
            f"현재 선택된 개수: {len(selected_stops)}"
        )
        return

    # 5. 정류장 상세정보 준비
    stop_info = (
        stop_history_df[
            [
                "정류장아이디",
                "정류장명",
                "링크아이디",
                "X좌표",
                "Y좌표",
            ]
        ]
        .drop_duplicates(
            subset=["정류장아이디"],
            keep="last",
        )
    )

    # 6. 노선 정류장과 상세정보 결합
    selected_stops = (
        selected_stops
        .merge(
            stop_info,
            on="정류장아이디",
            how="left",
        )
        .drop_duplicates(
            subset=["정류장순서", "정류장아이디"],
            keep="first",
        )
        .sort_values("정류장순서")
        .reset_index(drop=True)
    )

    selected_stops["X좌표"] = pd.to_numeric(
        selected_stops["X좌표"],
        errors="coerce",
    )
    selected_stops["Y좌표"] = pd.to_numeric(
        selected_stops["Y좌표"],
        errors="coerce",
    )

    # 7. 선택한 정류장 출력
    selected_stop_result = selected_stops[
        [
            "정류장순서",
            "정류장아이디",
            "정류장명",
            "X좌표",
            "Y좌표",
            "링크아이디",
            "GIS거리",
            "누적거리",
            "확정거리",
        ]
    ]

    print("\n")
    print("=" * 110)
    print("선택한 연속 정류장")
    print("=" * 110)
    print(selected_stop_result.to_string(index=False))
    print("=" * 110)

    # 8. BMS LINK_ID와 KTDB LINK_ID 비교
    check_bms_link_ids(
        selected_stops,
        link_gdf,
    )

    # 9. 정류장별 최근접 KTDB LINK 검색
    nearest_link_df = find_nearest_link(
        selected_stops,
        link_gdf,
    )

    if nearest_link_df.empty:
        print("최근접 KTDB LINK를 찾지 못했습니다.")
        return

    # 10. 매칭 거리 점검
    max_match_distance = nearest_link_df[
        "링크매칭거리_m"
    ].max()

    print("\n========== 최근접 LINK 매칭 결과 ==========")

    if pd.isna(max_match_distance):
        print("Link 매칭 거리 계산 결과가 비어 있습니다.")
        return

    if max_match_distance <= 30:
        print(
            f"정상 범위로 보입니다. "
            f"최대 Link 매칭 거리: {max_match_distance:.2f}m"
        )
        print(
            "다음 단계에서 F_NODE와 T_NODE를 이용해 "
            "도로 그래프를 생성할 수 있습니다."
        )

    elif max_match_distance <= 100:
        print(
            f"Link가 매칭되었지만 거리가 조금 큽니다. "
            f"최대 거리: {max_match_distance:.2f}m"
        )
        print(
            "정류장과 도로 중앙선의 위치 차이일 수 있으므로 "
            "ROAD_NAME을 확인해야 합니다."
        )

    else:
        print(
            f"Link 매칭 거리가 비정상적으로 큽니다. "
            f"최대 거리: {max_match_distance:.2f}m"
        )
        print(
            "BMS_CRS가 EPSG:5181이 맞는지 추가 확인이 필요합니다."
        )


if __name__ == "__main__":
    main()