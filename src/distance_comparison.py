from pathlib import Path

import pandas as pd


def compare_bms_ktdb_distances(
    matched_stop_df: pd.DataFrame,
    shortest_path_df: pd.DataFrame,
    output_path: str = "output/distance_comparison.csv",
) -> pd.DataFrame:
    """
    연속 정류장 구간별 BMS 거리와 KTDB 최단거리 결과를 비교한다.

    주의:
    BMS의 GIS거리/확정거리는 해당 행의 정류장에 도착하기까지의
    구간거리로 해석한다. 따라서 A → B 구간 비교에는 B 정류장 행의
    GIS거리와 확정거리를 사용한다.
    """

    if matched_stop_df.empty:
        raise ValueError("정류장 매칭 결과가 비어 있습니다.")

    if shortest_path_df.empty:
        raise ValueError("KTDB 최단거리 결과가 비어 있습니다.")

    required_stop_columns = [
        "정류장순서",
        "정류장명",
        "GIS거리",
        "확정거리",
    ]

    missing_stop_columns = [
        column
        for column in required_stop_columns
        if column not in matched_stop_df.columns
    ]

    if missing_stop_columns:
        raise KeyError(
            "정류장 데이터에 필요한 컬럼이 없습니다: "
            f"{missing_stop_columns}"
        )

    required_path_columns = [
        "출발정류장",
        "도착정류장",
        "도로거리(m)",
    ]

    missing_path_columns = [
        column
        for column in required_path_columns
        if column not in shortest_path_df.columns
    ]

    if missing_path_columns:
        raise KeyError(
            "최단거리 결과에 필요한 컬럼이 없습니다: "
            f"{missing_path_columns}"
        )

    stops = (
        matched_stop_df
        .sort_values("정류장순서")
        .reset_index(drop=True)
        .copy()
    )

    segment_rows = []

    for index in range(len(stops) - 1):
        start_stop = stops.iloc[index]
        end_stop = stops.iloc[index + 1]

        segment_rows.append(
            {
                "출발정류장": start_stop["정류장명"],
                "도착정류장": end_stop["정류장명"],
                "BMS_GIS거리(m)": pd.to_numeric(
                    end_stop["GIS거리"],
                    errors="coerce",
                ),
                "BMS_확정거리(m)": pd.to_numeric(
                    end_stop["확정거리"],
                    errors="coerce",
                ),
            }
        )

    bms_segment_df = pd.DataFrame(segment_rows)

    comparison_df = bms_segment_df.merge(
        shortest_path_df[
            [
                "출발정류장",
                "도착정류장",
                "도로거리(m)",
            ]
        ],
        on=[
            "출발정류장",
            "도착정류장",
        ],
        how="left",
    )

    comparison_df = comparison_df.rename(
        columns={
            "도로거리(m)": "KTDB_최단거리(m)",
        }
    )

    comparison_df["확정거리대비_차이(m)"] = (
        comparison_df["KTDB_최단거리(m)"]
        - comparison_df["BMS_확정거리(m)"]
    ).round(2)

    comparison_df["GIS거리대비_차이(m)"] = (
        comparison_df["KTDB_최단거리(m)"]
        - comparison_df["BMS_GIS거리(m)"]
    ).round(2)

    comparison_df["확정거리대비_오차율(%)"] = (
        comparison_df["확정거리대비_차이(m)"]
        / comparison_df["BMS_확정거리(m)"]
        * 100
    ).round(2)

    comparison_df["GIS거리대비_오차율(%)"] = (
        comparison_df["GIS거리대비_차이(m)"]
        / comparison_df["BMS_GIS거리(m)"]
        * 100
    ).round(2)

    print()
    print("=" * 140)
    print("BMS 거리와 KTDB 최단거리 비교")
    print("=" * 140)
    print(comparison_df.to_string(index=False))
    print("=" * 140)

    output_file = Path(output_path)
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    comparison_df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"비교 결과 CSV 저장: {output_file.resolve()}")

    return comparison_df