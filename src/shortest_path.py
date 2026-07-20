import networkx as nx
import pandas as pd


def calculate_shortest_paths(
    graph: nx.DiGraph,
    matched_stop_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    대표 NODE를 이용하여
    연속된 정류장 간 최단 도로거리를 계산한다.
    """

    print()
    print("=" * 100)
    print("정류장 간 최단 도로거리 계산")
    print("=" * 100)

    result = []

    matched_stop_df = matched_stop_df.sort_values(
        "정류장순서"
    ).reset_index(drop=True)

    for i in range(len(matched_stop_df) - 1):

        current = matched_stop_df.iloc[i]
        next_stop = matched_stop_df.iloc[i + 1]

        source = int(current["대표_NODE"])
        target = int(next_stop["대표_NODE"])

        try:

            distance = nx.shortest_path_length(
                graph,
                source=source,
                target=target,
                weight="weight",
            )

            path = nx.shortest_path(
                graph,
                source=source,
                target=target,
                weight="weight",
            )

        except nx.NetworkXNoPath:

            distance = None
            path = []

        result.append(
            {
                "출발정류장": current["정류장명"],
                "도착정류장": next_stop["정류장명"],
                "출발NODE": source,
                "도착NODE": target,
                "도로거리(m)": distance,
                "경유NODE수": len(path),
            }
        )

    result_df = pd.DataFrame(result)

    print(result_df.to_string(index=False))

    print("=" * 100)

    return result_df