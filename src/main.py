import pandas as pd

from load_data import load_bms_data, load_ktdb_data
from matcher import (
    assign_link_projection,
    assign_representative_node,
    check_bms_link_ids,
    find_nearest_link,
)
from map_visualizer import create_link_matching_map
from graph_builder import build_graph
from shortest_path import (
    calculate_projected_shortest_paths,
    calculate_shortest_paths,
)
from distance_comparison import compare_bms_ktdb_distances
from path_export import export_selected_path_links

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 240)
pd.set_option("display.max_colwidth", 50)
pd.set_option("display.expand_frame_repr", False)


TARGET_ROUTE_ID = 208000016
START_SEQUENCE = 68
STOP_COUNT = 3


def main() -> None:

    print("=" * 80)
    print("국토부 Node-Link 기반 버스 정류장 거리 계산")
    print("=" * 80)

    datasets = load_bms_data()
    route_stop_df = datasets["route_stop"]
    stop_history_df = datasets["stop_history"]

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

    print()
    print("=" * 110)
    print("선택한 연속 정류장")
    print("=" * 110)
    print(selected_stop_result.to_string(index=False))
    print("=" * 110)

    check_bms_link_ids(
        selected_stops,
        link_gdf,
    )

    nearest_link_df = find_nearest_link(
        selected_stops,
        link_gdf,
    )

    if nearest_link_df.empty:
        print("최근접 KTDB LINK를 찾지 못했습니다.")
        return

    projected_stop_df = assign_link_projection(
        nearest_link_df,
    )

    if projected_stop_df.empty:
        print("정류장 LINK 내부 투영 결과가 비어 있습니다.")
        return

    matched_stop_df = assign_representative_node(
        projected_stop_df,
        node_gdf,
    )

    graph = build_graph(link_gdf)

    representative_distance_result = calculate_shortest_paths(
        graph,
        matched_stop_df,
    )

    selected_path_link_result = export_selected_path_links(
    projected_distance_result,
    link_gdf,
    output_path="output/selected_path_links.csv",
    )

    if selected_path_link_result.empty:
        print("선택 경로 Link 분석 결과가 비어 있습니다.")

    projected_distance_result = calculate_projected_shortest_paths(
        graph,
        projected_stop_df,
    )

    representative_comparison_result = compare_bms_ktdb_distances(
        selected_stops,
        representative_distance_result,
        output_path="output/representative_distance_comparison.csv",
    )

    if representative_comparison_result.empty:
        print("기존 대표 NODE 방식 거리 비교 결과가 비어 있습니다.")

    projected_result_for_comparison = projected_distance_result.copy()
    projected_result_for_comparison["도로거리(m)"] = (
        projected_result_for_comparison["개선도로거리(m)"]
    )

    projected_comparison_result = compare_bms_ktdb_distances(
        selected_stops,
        projected_result_for_comparison,
        output_path="output/projected_distance_comparison.csv",
    )

    if projected_comparison_result.empty:
        print("개선된 투영 방식 거리 비교 결과가 비어 있습니다.")

    map_file_path = create_link_matching_map(
        matched_stop_df,
        link_gdf,
        node_gdf=node_gdf,
        shortest_path_df=projected_distance_result,
        output_path="output/projected_link_matching_map.html",
    )

    print("\n========== 지도 생성 완료 ==========")
    print(f"지도 파일: {map_file_path}")

    max_match_distance = projected_stop_df[
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
            "정류장의 Link 내부 투영점과 "
            "F_NODE/T_NODE 방향 부분거리까지 계산되었습니다."
        )

    elif max_match_distance <= 100:
        print(
            f"Link가 매칭되었지만 거리가 조금 큽니다. "
            f"최대 거리: {max_match_distance:.2f}m"
        )
        print(
            "정류장과 도로 중앙선의 위치 차이일 수 있으므로 "
            "지도와 ROAD_NAME을 함께 확인해야 합니다."
        )

    else:
        print(
            f"Link 매칭 거리가 비정상적으로 큽니다. "
            f"최대 거리: {max_match_distance:.2f}m"
        )
        print(
            "BMS_CRS가 EPSG:5181이 맞는지 추가 확인이 필요합니다."
        )

    print("\n========== 실행 결과 파일 ==========")
    print(
        "기존 대표 NODE 비교 CSV: "
        "output/representative_distance_comparison.csv"
    )
    print(
        "개선 투영 방식 비교 CSV: "
        "output/projected_distance_comparison.csv"
    )
    print(
        "개선 투영 방식 지도: "
        "output/projected_link_matching_map.html"
    )


if __name__ == "__main__":
    main()