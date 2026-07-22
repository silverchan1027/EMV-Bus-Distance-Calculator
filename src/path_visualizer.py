from __future__ import annotations

import folium
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def _normalize_node_id(value) -> str:
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
        subset=["F_NODE", "T_NODE", "geometry"]
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

    return result.sort_values(
        "PATH_ORDER"
    ).reset_index(drop=True)


def _get_node_point_from_link(
    link_row: pd.Series,
    node_id,
) -> Point:
    """
    Link geometry 시작점=F_NODE, 끝점=T_NODE라고 보고
    지정 NODE의 좌표를 반환한다.
    """

    geometry = link_row["geometry"]

    if geometry is None or geometry.is_empty:
        raise ValueError(
            f"LINK geometry가 비어 있습니다: {link_row['LINK_ID']}"
        )

    coordinates = list(geometry.coords)

    node_key = _normalize_node_id(node_id)
    f_node_key = _normalize_node_id(link_row["F_NODE"])
    t_node_key = _normalize_node_id(link_row["T_NODE"])

    if node_key == f_node_key:
        return Point(coordinates[0])

    if node_key == t_node_key:
        return Point(coordinates[-1])

    raise ValueError(
        "경로 NODE가 Link의 F_NODE/T_NODE와 일치하지 않습니다: "
        f"LINK_ID={link_row['LINK_ID']}, NODE_ID={node_id}"
    )


def build_path_node_points(
    path_nodes: list,
    path_links: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    경로 NODE 목록을 번호가 붙은 Point GeoDataFrame으로 변환한다.
    """

    node_rows = []

    for node_order, node_id in enumerate(path_nodes):

        if node_order == 0:
            related_link = path_links.iloc[0]

        elif node_order == len(path_nodes) - 1:
            related_link = path_links.iloc[-1]

        else:
            related_link = path_links.iloc[node_order - 1]

        node_point = _get_node_point_from_link(
            related_link,
            node_id,
        )

        if node_order == 0:
            node_role = "출발"

        elif node_order == len(path_nodes) - 1:
            node_role = "도착"

        else:
            node_role = "경유"

        node_rows.append(
            {
                "DISPLAY_ORDER": node_order + 1,
                "NODE_ID": node_id,
                "NODE_ROLE": node_role,
                "geometry": node_point,
            }
        )

    return gpd.GeoDataFrame(
        node_rows,
        geometry="geometry",
        crs=path_links.crs,
    )


def _create_numbered_node_icon(
    display_order: int,
    node_role: str,
) -> folium.DivIcon:

    if node_role == "출발":
        background = "#198754"
        text_color = "#ffffff"

    elif node_role == "도착":
        background = "#dc3545"
        text_color = "#ffffff"

    else:
        background = "#ffffff"
        text_color = "#111111"

    html = f"""
    <div style="
        width:28px;
        height:28px;
        border-radius:50%;
        background:{background};
        color:{text_color};
        border:2px solid #111111;
        font-size:13px;
        font-weight:700;
        text-align:center;
        line-height:24px;
        box-sizing:border-box;
        box-shadow:0 1px 4px rgba(0,0,0,0.45);
    ">{display_order}</div>
    """

    return folium.DivIcon(
        html=html,
        icon_size=(28, 28),
        icon_anchor=(14, 14),
    )


def add_shortest_path_layer(
    map_object: folium.Map,
    shortest_path_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
) -> folium.FeatureGroup:
    """
    Dijkstra 경로 Link와 모든 경로 NODE 번호를 지도에 표시한다.
    """

    if shortest_path_df.empty:
        raise ValueError("최단경로 결과가 비어 있습니다.")

    path_df = shortest_path_df.copy()

    if (
        "도로거리(m)" not in path_df.columns
        and "개선도로거리(m)" in path_df.columns
    ):
        path_df["도로거리(m)"] = path_df["개선도로거리(m)"]

    required_columns = [
        "출발정류장",
        "도착정류장",
        "도로거리(m)",
        "경로NODE",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in path_df.columns
    ]

    if missing_columns:
        raise KeyError(
            f"최단경로 결과에 필요한 컬럼이 없습니다: {missing_columns}"
        )

    path_layer = folium.FeatureGroup(
        name="Dijkstra 실제 도로 최단경로",
        show=True,
    )

    node_layer = folium.FeatureGroup(
        name="Dijkstra 경로 NODE 번호",
        show=True,
    )

    for section_index, (_, path_row) in enumerate(
        path_df.iterrows(),
        start=1,
    ):
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

        path_type_text = ""

        if (
            "경로유형" in path_row.index
            and pd.notna(path_row["경로유형"])
        ):
            path_type_text = (
                f"선택 조합: {path_row['경로유형']}<br>"
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
                f"구간 번호: {section_index}<br>"
                f"구간: {section_title}<br>"
                f"{path_type_text}"
                f"경로 순서: {int(link['PATH_ORDER']) + 1}<br>"
                f"LINK_ID: {link['LINK_ID']}<br>"
                f"F_NODE: {link['F_NODE']}<br>"
                f"T_NODE: {link['T_NODE']}<br>"
                f"도로명: {road_name_text}<br>"
                f"Link 길이: {link['LENGTH']} m<br>"
                f"구간 최단거리: {path_row['도로거리(m)']} m"
            )

            folium.GeoJson(
                data=link.geometry.__geo_interface__,
                tooltip=(
                    f"[구간 {section_index}] {section_title} / "
                    f"LINK_ID {link['LINK_ID']}"
                ),
                popup=folium.Popup(
                    popup_text,
                    max_width=400,
                ),
                style_function=lambda feature: {
                    "color": "#0d6efd",
                    "weight": 8,
                    "opacity": 0.9,
                },
            ).add_to(path_layer)

        path_node_points = build_path_node_points(
            path_nodes,
            path_links,
        ).to_crs(epsg=4326)

        for _, node_row in path_node_points.iterrows():

            node_popup = (
                f"<b>Dijkstra 경로 NODE</b><br>"
                f"구간 번호: {section_index}<br>"
                f"구간: {section_title}<br>"
                f"경로 내 순서: {node_row['DISPLAY_ORDER']} / "
                f"{len(path_nodes)}<br>"
                f"NODE 역할: {node_row['NODE_ROLE']}<br>"
                f"NODE_ID: {node_row['NODE_ID']}<br>"
                f"{path_type_text}"
                f"구간 최단거리: {path_row['도로거리(m)']} m"
            )

            folium.Marker(
                location=[
                    node_row.geometry.y,
                    node_row.geometry.x,
                ],
                tooltip=(
                    f"[구간 {section_index}] "
                    f"{int(node_row['DISPLAY_ORDER'])}번 NODE / "
                    f"{node_row['NODE_ID']}"
                ),
                popup=folium.Popup(
                    node_popup,
                    max_width=400,
                ),
                icon=_create_numbered_node_icon(
                    int(node_row["DISPLAY_ORDER"]),
                    str(node_row["NODE_ROLE"]),
                ),
            ).add_to(node_layer)

    path_layer.add_to(map_object)
    node_layer.add_to(map_object)

    return path_layer


def get_shortest_path_bounds(
    shortest_path_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
) -> list[list[float]] | None:

    if shortest_path_df.empty:
        return None

    if "경로NODE" not in shortest_path_df.columns:
        raise KeyError(
            "최단경로 결과에 '경로NODE' 컬럼이 없습니다."
        )

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

    min_x, min_y, max_x, max_y = (
        combined_wgs84.total_bounds
    )

    return [
        [min_y, min_x],
        [max_y, max_x],
    ]