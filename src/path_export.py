from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from path_visualizer import find_path_links


def export_selected_path_links(
    shortest_path_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
    output_path: str = "output/selected_path_links.csv",
) -> pd.DataFrame:
    """
    Dijkstra가 선택한 경로의 KTDB Link 정보를
    구간별·경로순서별로 CSV에 저장한다.
    """

    if shortest_path_df.empty:
        raise ValueError("최단경로 결과가 비어 있습니다.")

    required_path_columns = [
        "출발정류장",
        "도착정류장",
        "경로NODE",
    ]

    missing_path_columns = [
        column
        for column in required_path_columns
        if column not in shortest_path_df.columns
    ]

    if missing_path_columns:
        raise KeyError(
            "최단경로 결과에 필요한 컬럼이 없습니다: "
            f"{missing_path_columns}"
        )

    if link_gdf.empty:
        raise ValueError("KTDB Link 데이터가 비어 있습니다.")

    result_list = []

    # KTDB Link에서 분석할 속성
    analysis_columns = [
        "LINK_ID",
        "ROAD_NAME",
        "ROAD_TYPE",
        "ROAD_USE",
        "CONNECT",
        "MULTI_LINK",
        "ROAD_RANK",
        "LANES",
        "MAX_SPD",
    ]

    available_analysis_columns = [
        column
        for column in analysis_columns
        if column in link_gdf.columns
    ]

    link_attribute_lookup = (
        link_gdf[
            available_analysis_columns
        ]
        .drop_duplicates(
            subset=["LINK_ID"],
            keep="first",
        )
        .copy()
    )

    for section_number, (_, path_row) in enumerate(
        shortest_path_df.iterrows(),
        start=1,
    ):
        path_nodes = path_row["경로NODE"]

        if (
            not isinstance(path_nodes, list)
            or len(path_nodes) < 2
        ):
            continue

        path_links = find_path_links(
            path_nodes,
            link_gdf,
        )

        if path_links.empty:
            continue

        # find_path_links 결과에 도로 속성 추가
        path_links = path_links.merge(
            link_attribute_lookup,
            on="LINK_ID",
            how="left",
            suffixes=("", "_KTDB"),
        )

        path_links["구간번호"] = section_number
        path_links["출발정류장"] = path_row["출발정류장"]
        path_links["도착정류장"] = path_row["도착정류장"]

        if (
            "경로유형" in path_row.index
            and pd.notna(path_row["경로유형"])
        ):
            path_links["경로유형"] = path_row["경로유형"]
        else:
            path_links["경로유형"] = ""

        result_list.append(
            pd.DataFrame(
                path_links.drop(
                    columns="geometry",
                    errors="ignore",
                )
            )
        )

    if not result_list:
        result_df = pd.DataFrame()

    else:
        result_df = pd.concat(
            result_list,
            ignore_index=True,
        )

        # 경로 순서를 사람이 보기 좋게 1부터 시작
        result_df["PATH_ORDER"] = (
            pd.to_numeric(
                result_df["PATH_ORDER"],
                errors="coerce",
            )
            + 1
        )

        result_df["LENGTH"] = pd.to_numeric(
            result_df["LENGTH"],
            errors="coerce",
        ).round(2)

        final_columns = [
            "구간번호",
            "출발정류장",
            "도착정류장",
            "경로유형",
            "PATH_ORDER",
            "PATH_FROM_NODE",
            "PATH_TO_NODE",
            "LINK_ID",
            "F_NODE",
            "T_NODE",
            "LENGTH",
            "ROAD_NAME",
            "ROAD_TYPE",
            "ROAD_USE",
            "CONNECT",
            "MULTI_LINK",
            "ROAD_RANK",
            "LANES",
            "MAX_SPD",
        ]

        existing_final_columns = [
            column
            for column in final_columns
            if column in result_df.columns
        ]

        result_df = result_df[
            existing_final_columns
        ].copy()

    output_file = Path(output_path)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("=" * 170)
    print("Dijkstra 선택 경로 LINK 분석")
    print("=" * 170)

    if result_df.empty:
        print("저장할 경로 Link가 없습니다.")
    else:
        print(result_df.to_string(index=False))

    print("=" * 170)
    print(
        f"경로 Link CSV 저장: "
        f"{output_file.resolve()}"
    )

    return result_df