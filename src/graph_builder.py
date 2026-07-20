import time

import geopandas as gpd
import networkx as nx


def build_graph(
    link_gdf: gpd.GeoDataFrame,
) -> nx.DiGraph:
    """
    KTDB Link 데이터를 이용하여 도로 그래프 생성

    Parameters
    ----------
    link_gdf : GeoDataFrame
        KTDB Link 데이터

    Returns
    -------
    nx.DiGraph
        도로 그래프
    """

    print()
    print("=" * 100)
    print("KTDB 도로 그래프 생성")
    print("=" * 100)

    start_time = time.time()

    if link_gdf.empty:
        raise ValueError("KTDB Link 데이터가 비어 있습니다.")

    required_columns = [
        "F_NODE",
        "T_NODE",
        "LENGTH",
    ]

    missing_columns = [
        c for c in required_columns
        if c not in link_gdf.columns
    ]

    if missing_columns:
        raise KeyError(
            f"필수 컬럼이 없습니다 : {missing_columns}"
        )

    # 필요한 컬럼만 사용
    valid_links = (
        link_gdf[required_columns]
        .dropna()
        .copy()
    )

    graph = nx.DiGraph()

    # iterrows()보다 훨씬 빠름
    for row in valid_links.itertuples(index=False):

        f_node = int(row.F_NODE)
        t_node = int(row.T_NODE)
        length = float(row.LENGTH)

        # 양방향 그래프
        graph.add_edge(
            f_node,
            t_node,
            weight=length,
        )

        graph.add_edge(
            t_node,
            f_node,
            weight=length,
        )

    elapsed = time.time() - start_time

    print(f"노드 수 : {graph.number_of_nodes():,}")
    print(f"간선 수 : {graph.number_of_edges():,}")
    print(f"생성 시간 : {elapsed:.2f}초")
    print("=" * 100)

    return graph