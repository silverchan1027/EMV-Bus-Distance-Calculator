from __future__ import annotations

import folium
import geopandas as gpd
import pandas as pd


def _normalize_node_id(value) -> str:
    """
    NODE ID 자료형 차이를 피하기 위해 문자열로 정규화한다.
    """
    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text


def find_path_links(
    path_nodes: list,
    link_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    최단경로 NODE 목록을 이용하여 각 NODE 쌍에 대응하는
    KTDB Link geometry를 순서대로 찾는다.

    Parameters
    ----------
    path_nodes : list
        Dijkstra 최단경로 NODE 목록
    link_gdf : GeoDataFrame
        KTDB Link 데이터

    Returns
    -------
    GeoDataFrame
        최단경로 순서대로 정렬된 KTDB Link 목록
    """

    if not path_nodes or len(path_nodes) < 2:
        return gpd.GeoDataFrame(
            columns=[
                "PATH_ORDER",
                "PATH_FROM_NODE",
                "PATH_TO_NODE",
                "LINK_ID",
                "F_NODE",
                "T_NODE",
                "LENGTH",
                "ROAD_NAME",
                "geometry",
            ],
            geometry="geometry",
            crs=link_gdf.crs,
        )

    if link_gdf.empty:
        raise ValueError("KTDB Link 데이터가 비어 있습니다.")

    if link_gdf.crs is None:
        raise ValueError("KTDB Link 좌표계 정보가 없습니다.")

    required_columns = [
        "LINK_ID",
        "F_NODE",
        "T_NODE",
        "LENGTH",
        "geometry",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in link_gdf.columns
    ]

    if missing_columns:
        raise KeyError(
            f"KTDB Link 데이터에 필요한 컬럼이 없습니다: {missing_columns}"
        )

    links = link_gdf.copy()

    links["F_NODE_KEY"] = links["F_NODE"].map(_normalize_node_id)
    links["T_NODE_KEY"] = links["T_NODE"].map(_normalize_node_id)

    lookup_columns = [
        "LINK_ID",
        "F_NODE",
        "T_NODE",
        "LENGTH",
        "geometry",
        "F_NODE_KEY",
        "T_NODE_KEY",
    ]

    if "ROAD_NAME" in links.columns:
        lookup_columns.insert(4, "ROAD_NAME")

    links = links[lookup_columns].dropna(
        subset=[
            "F_NODE",
            "T_NODE",
            "geometry",
        ]
    )

    selected_rows = []

    for order, (from_node, to_node) in enumerate(
        zip(path_nodes[:-1], path_nodes[1:])
    ):
        from_key = _normalize_node_id(from_node)
        to_key = _normalize_node_id(to_node)

        candidates = links[
            (
                (links["F_NODE_KEY"] == from_key)
                & (links["T_NODE_KEY"] == to_key)
            )
            |
            (
                (links["F_NODE_KEY"] == to_key)
                & (links["T_NODE_KEY"] == from_key)
            )
        ].copy()

        if candidates.empty:
            raise ValueError(
                "최단경로 NODE 쌍에 대응하는 KTDB Link를 찾지 못했습니다: "
                f"{from_node} -> {to_node}"
            )

        candidates["LENGTH_NUMERIC"] = pd.to_numeric(
            candidates["LENGTH"],
            errors="coerce",
        )

        candidates = candidates.sort_values(
            "LENGTH_NUMERIC",
            na_position="last",
        )

        selected = candidates.iloc[0].copy()

        selected["PATH_ORDER"] = order
        selected["PATH_FROM_NODE"] = from_node
        selected["PATH_TO_NODE"] = to_node

        selected_rows.append(selected)

    result = gpd.GeoDataFrame(
        selected_rows,
        geometry="geometry",
        crs=link_gdf.crs,
    )

    result = result.sort_values(
        "PATH_ORDER"
    ).reset_index(drop=True)

    return result


def add_shortest_path_layer(
    map_object: folium.Map,
    shortest_path_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
) -> folium.FeatureGroup:
    """
    Dijkstra 최단경로를 실제 KTDB Link geometry로 지도에 추가한다.

    Parameters
    ----------
    map_object : folium.Map
        최단경로를 추가할 Folium 지도
    shortest_path_df : DataFrame
        calculate_shortest_paths() 결과
    link_gdf : GeoDataFrame
        KTDB Link 데이터

    Returns
    -------
    folium.FeatureGroup
        생성된 최단경로 레이어
    """

    if shortest_path_df.empty:
        raise ValueError("최단경로 결과가 비어 있습니다.")

    required_columns = [
        "출발정류장",
        "도착정류장",
        "도로거리(m)",
        "경로NODE",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in shortest_path_df.columns
    ]

    if missing_columns:
        raise KeyError(
            f"최단경로 결과에 필요한 컬럼이 없습니다: {missing_columns}"
        )

    path_layer = folium.FeatureGroup(
        name="Dijkstra 실제 도로 최단경로",
        show=True,
    )

    for _, path_row in shortest_path_df.iterrows():
        path_nodes = path_row["경로NODE"]

        if not isinstance(path_nodes, list) or len(path_nodes) < 2:
            continue

        path_links = find_path_links(
            path_nodes,
            link_gdf,
        )

        if path_links.empty:
            continue

        path_links_wgs84 = path_links.to_crs(epsg=4326)

        section_title = (
            f"{path_row['출발정류장']} → "
            f"{path_row['도착정류장']}"
        )

        for _, link in path_links_wgs84.iterrows():
            road_name = link.get("ROAD_NAME", "")
            road_name_text = (
                ""
                if pd.isna(road_name)
                else str(road_name)
            )

            popup_text = (
                f"<b>Dijkstra 최단경로</b><br>"
                f"구간: {section_title}<br>"
                f"경로 순서: {int(link['PATH_ORDER']) + 1}<br>"
                f"LINK_ID: {link['LINK_ID']}<br>"
                f"F_NODE: {link['F_NODE']}<br>"
                f"T_NODE: {link['T_NODE']}<br>"
                f"도로명: {road_name_text}<br>"
                f"Link 길이: {link['LENGTH']} m<br>"
                f"구간 최단거리: {path_row['도로거리(m)']} m"
            )

            tooltip_text = (
                f"{section_title} / "
                f"LINK_ID {link['LINK_ID']} / "
                f"{road_name_text}"
            )

            folium.GeoJson(
                data=link.geometry.__geo_interface__,
                tooltip=tooltip_text,
                popup=folium.Popup(
                    popup_text,
                    max_width=380,
                ),
                style_function=lambda feature: {
                    "weight": 8,
                    "opacity": 0.9,
                },
            ).add_to(path_layer)

    path_layer.add_to(map_object)

    return path_layer


def get_shortest_path_bounds(
    shortest_path_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
) -> list[list[float]] | None:
    """
    최단경로 전체를 포함하는 Folium fit_bounds용 범위를 반환한다.
    """

    if shortest_path_df.empty:
        return None

    all_path_links = []

    for path_nodes in shortest_path_df["경로NODE"]:
        if not isinstance(path_nodes, list) or len(path_nodes) < 2:
            continue

        path_links = find_path_links(
            path_nodes,
            link_gdf,
        )

        if not path_links.empty:
            all_path_links.append(path_links)

    if not all_path_links:
        return None

    combined = gpd.GeoDataFrame(
        pd.concat(
            all_path_links,
            ignore_index=True,
        ),
        geometry="geometry",
        crs=link_gdf.crs,
    )

    combined_wgs84 = combined.to_crs(epsg=4326)

    min_x, min_y, max_x, max_y = combined_wgs84.total_bounds

    return [
        [min_y, min_x],
        [max_y, max_x],
    ]