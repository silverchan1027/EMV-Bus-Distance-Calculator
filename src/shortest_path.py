import networkx as nx
import pandas as pd


def _normalize_node_id(value) -> int:
    """
    NODE ID를 NetworkX 그래프에서 사용하는 int 형식으로 변환한다.
    """

    if pd.isna(value):
        raise ValueError("NODE ID가 비어 있습니다.")

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return int(text)


def calculate_shortest_paths(
    graph: nx.DiGraph,
    matched_stop_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    기존 대표 NODE 방식을 이용하여 연속 정류장 간 최단거리를 계산한다.

    이 함수는 개선 전·후 결과 비교를 위해 유지한다.
    """

    print()
    print("=" * 100)
    print("기존 대표 NODE 방식 최단 도로거리 계산")
    print("=" * 100)

    required_columns = [
        "정류장순서",
        "정류장명",
        "대표_NODE",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in matched_stop_df.columns
    ]

    if missing_columns:
        raise KeyError(
            f"대표 NODE 계산에 필요한 컬럼이 없습니다: {missing_columns}"
        )

    stops = (
        matched_stop_df
        .sort_values("정류장순서")
        .reset_index(drop=True)
    )

    result = []

    for index in range(len(stops) - 1):
        current = stops.iloc[index]
        next_stop = stops.iloc[index + 1]

        source = _normalize_node_id(current["대표_NODE"])
        target = _normalize_node_id(next_stop["대표_NODE"])

        try:
            distance, path = nx.single_source_dijkstra(
                graph,
                source=source,
                target=target,
                weight="weight",
            )

        except (nx.NetworkXNoPath, nx.NodeNotFound):
            distance = None
            path = []

        result.append(
            {
                "출발정류장": current["정류장명"],
                "도착정류장": next_stop["정류장명"],
                "출발NODE": source,
                "도착NODE": target,
                "도로거리(m)": (
                    round(float(distance), 2)
                    if distance is not None
                    else None
                ),
                "경유NODE수": len(path),
                "경로NODE": path,
            }
        )

    result_df = pd.DataFrame(result)

    print(result_df.to_string(index=False))

    print()
    print("=" * 100)
    print("기존 대표 NODE 방식 경로")
    print("=" * 100)

    for _, row in result_df.iterrows():
        print()
        print(f"{row['출발정류장']} → {row['도착정류장']}")

        if row["경로NODE"]:
            print(" -> ".join(map(str, row["경로NODE"])))
        else:
            print("경로 없음")

    print("=" * 100)

    return result_df


def _build_endpoint_options(
    stop: pd.Series,
) -> list[dict]:
    """
    정류장 투영점에서 F_NODE 또는 T_NODE로 이동하는 두 가지 선택지를 만든다.
    """

    return [
        {
            "node_type": "F_NODE",
            "node": _normalize_node_id(stop["F_NODE"]),
            "partial_distance": float(
                stop["F_NODE방향_부분거리_m"]
            ),
        },
        {
            "node_type": "T_NODE",
            "node": _normalize_node_id(stop["T_NODE"]),
            "partial_distance": float(
                stop["T_NODE방향_부분거리_m"]
            ),
        },
    ]


def _calculate_same_link_distance(
    current: pd.Series,
    next_stop: pd.Series,
) -> dict | None:
    """
    두 정류장이 같은 Link 위에 있을 때 투영점 사이의 Link 내부 거리를 계산한다.

    현재 그래프가 양방향으로 구성되어 있으므로 방향 제약 없이
    두 투영점 사이의 절대 거리 차이를 사용한다.
    """

    current_link = str(current["LINK_ID"]).strip()
    next_link = str(next_stop["LINK_ID"]).strip()

    if current_link != next_link:
        return None

    current_from_distance = float(
        current["F_NODE방향_부분거리_m"]
    )
    next_from_distance = float(
        next_stop["F_NODE방향_부분거리_m"]
    )

    internal_distance = abs(
        next_from_distance - current_from_distance
    )

    return {
        "출발접속NODE구분": "동일_LINK",
        "출발접속NODE": None,
        "출발부분거리(m)": 0.0,
        "NODE간거리(m)": 0.0,
        "도착접속NODE구분": "동일_LINK",
        "도착접속NODE": None,
        "도착부분거리(m)": 0.0,
        "개선도로거리(m)": round(internal_distance, 2),
        "경유NODE수": 0,
        "경로NODE": [],
        "경로유형": "동일_LINK_내부거리",
    }


def calculate_projected_shortest_paths(
    graph: nx.DiGraph,
    projected_stop_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Link 내부 투영점을 이용하여 연속 정류장 간 개선 도로거리를 계산한다.

    서로 다른 Link에 있는 두 정류장에 대해 다음 네 가지 조합을 비교한다.

    1. 출발 F_NODE → 도착 F_NODE
    2. 출발 F_NODE → 도착 T_NODE
    3. 출발 T_NODE → 도착 F_NODE
    4. 출발 T_NODE → 도착 T_NODE

    총거리:
    출발 투영점→접속 NODE 부분거리
    + 접속 NODE 간 최단거리
    + 도착 접속 NODE→투영점 부분거리
    """

    print()
    print("=" * 150)
    print("LINK 내부 투영 방식 최단 도로거리 계산")
    print("=" * 150)

    required_columns = [
        "정류장순서",
        "정류장명",
        "LINK_ID",
        "F_NODE",
        "T_NODE",
        "F_NODE방향_부분거리_m",
        "T_NODE방향_부분거리_m",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in projected_stop_df.columns
    ]

    if missing_columns:
        raise KeyError(
            f"투영 방식 계산에 필요한 컬럼이 없습니다: {missing_columns}"
        )

    stops = (
        projected_stop_df
        .sort_values("정류장순서")
        .reset_index(drop=True)
    )

    result_rows = []
    combination_rows = []

    for index in range(len(stops) - 1):
        current = stops.iloc[index]
        next_stop = stops.iloc[index + 1]

        same_link_result = _calculate_same_link_distance(
            current,
            next_stop,
        )

        if same_link_result is not None:
            result_rows.append(
                {
                    "출발정류장": current["정류장명"],
                    "도착정류장": next_stop["정류장명"],
                    "출발LINK_ID": current["LINK_ID"],
                    "도착LINK_ID": next_stop["LINK_ID"],
                    **same_link_result,
                }
            )
            continue

        start_options = _build_endpoint_options(current)
        end_options = _build_endpoint_options(next_stop)

        candidates = []

        for start_option in start_options:
            for end_option in end_options:
                source = start_option["node"]
                target = end_option["node"]

                try:
                    node_distance, node_path = nx.single_source_dijkstra(
                        graph,
                        source=source,
                        target=target,
                        weight="weight",
                    )

                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    node_distance = None
                    node_path = []

                if node_distance is None:
                    total_distance = None
                else:
                    total_distance = (
                        start_option["partial_distance"]
                        + float(node_distance)
                        + end_option["partial_distance"]
                    )

                candidate = {
                    "출발정류장": current["정류장명"],
                    "도착정류장": next_stop["정류장명"],
                    "출발LINK_ID": current["LINK_ID"],
                    "도착LINK_ID": next_stop["LINK_ID"],
                    "출발접속NODE구분": start_option["node_type"],
                    "출발접속NODE": source,
                    "출발부분거리(m)": round(
                        start_option["partial_distance"],
                        2,
                    ),
                    "NODE간거리(m)": (
                        round(float(node_distance), 2)
                        if node_distance is not None
                        else None
                    ),
                    "도착접속NODE구분": end_option["node_type"],
                    "도착접속NODE": target,
                    "도착부분거리(m)": round(
                        end_option["partial_distance"],
                        2,
                    ),
                    "개선도로거리(m)": (
                        round(total_distance, 2)
                        if total_distance is not None
                        else None
                    ),
                    "경유NODE수": len(node_path),
                    "경로NODE": node_path,
                    "경로유형": (
                        f"{start_option['node_type']}"
                        f"→{end_option['node_type']}"
                    ),
                }

                candidates.append(candidate)
                combination_rows.append(candidate.copy())

        valid_candidates = [
            candidate
            for candidate in candidates
            if candidate["개선도로거리(m)"] is not None
        ]

        if not valid_candidates:
            result_rows.append(
                {
                    "출발정류장": current["정류장명"],
                    "도착정류장": next_stop["정류장명"],
                    "출발LINK_ID": current["LINK_ID"],
                    "도착LINK_ID": next_stop["LINK_ID"],
                    "출발접속NODE구분": None,
                    "출발접속NODE": None,
                    "출발부분거리(m)": None,
                    "NODE간거리(m)": None,
                    "도착접속NODE구분": None,
                    "도착접속NODE": None,
                    "도착부분거리(m)": None,
                    "개선도로거리(m)": None,
                    "경유NODE수": 0,
                    "경로NODE": [],
                    "경로유형": "경로없음",
                }
            )
            continue

        best_candidate = min(
            valid_candidates,
            key=lambda candidate: candidate["개선도로거리(m)"],
        )

        result_rows.append(best_candidate)

    result_df = pd.DataFrame(result_rows)
    combination_df = pd.DataFrame(combination_rows)

    print()
    print("선택된 최소거리 조합")
    print("-" * 150)
    print(result_df.to_string(index=False))
    print("-" * 150)

    if not combination_df.empty:
        print()
        print("검토한 F_NODE/T_NODE 조합 전체")
        print("-" * 150)

        display_columns = [
            "출발정류장",
            "도착정류장",
            "경로유형",
            "출발부분거리(m)",
            "NODE간거리(m)",
            "도착부분거리(m)",
            "개선도로거리(m)",
        ]

        print(
            combination_df[display_columns]
            .to_string(index=False)
        )
        print("-" * 150)

    print()
    print("선택된 개선 경로 NODE")
    print("-" * 150)

    for _, row in result_df.iterrows():
        print()
        print(
            f"{row['출발정류장']} → "
            f"{row['도착정류장']} "
            f"({row['경로유형']})"
        )

        if row["경로NODE"]:
            print(" -> ".join(map(str, row["경로NODE"])))
        else:
            print("동일 Link 내부 이동 또는 경로 없음")

    print("=" * 150)

    return result_df