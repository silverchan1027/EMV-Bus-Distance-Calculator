from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

from path_visualizer import (
    add_shortest_path_layer,
    get_shortest_path_bounds,
)


def create_link_matching_map(
    nearest_link_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
    node_gdf: gpd.GeoDataFrame | None = None,
    shortest_path_df: pd.DataFrame | None = None,
    output_path: str = "output/link_matching_map.html",
) -> str:
    """BMS 정류장, 매칭된 KTDB Link, Dijkstra 최단경로를 Folium 지도에 표시한다."""

    if nearest_link_df.empty:
        raise ValueError("지도에 표시할 최근접 Link 결과가 없습니다.")

    if link_gdf.empty:
        raise ValueError("KTDB Link 데이터가 비어 있습니다.")

    if link_gdf.crs is None:
        raise ValueError("KTDB Link 좌표계 정보가 없습니다.")

    required_columns = [
        "정류장순서",
        "정류장아이디",
        "정류장명",
        "KTDB_X",
        "KTDB_Y",
        "LINK_ID",
        "F_NODE",
        "T_NODE",
        "LENGTH",
        "ROAD_NAME",
        "링크매칭거리_m",
    ]

    missing_columns = [
        c for c in required_columns
        if c not in nearest_link_df.columns
    ]

    if missing_columns:
        raise KeyError(
            f"최근접 Link 결과에 필요한 컬럼이 없습니다: {missing_columns}"
        )

    stop_gdf = gpd.GeoDataFrame(
        nearest_link_df.copy(),
        geometry=gpd.points_from_xy(
            nearest_link_df["KTDB_X"],
            nearest_link_df["KTDB_Y"],
        ),
        crs=link_gdf.crs,
    )

    stop_wgs84 = stop_gdf.to_crs(epsg=4326)

    target_link_ids = set(
        nearest_link_df["LINK_ID"].dropna().astype(str)
    )

    matched_links = link_gdf[
        link_gdf["LINK_ID"].astype(str).isin(target_link_ids)
    ].copy()

    if matched_links.empty:
        raise ValueError("매칭된 KTDB Link geometry를 찾지 못했습니다.")

    matched_links_wgs84 = matched_links.to_crs(epsg=4326)

    center_latitude = stop_wgs84.geometry.y.mean()
    center_longitude = stop_wgs84.geometry.x.mean()

    map_object = folium.Map(
        location=[center_latitude, center_longitude],
        zoom_start=16,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    link_layer = folium.FeatureGroup(
        name="매칭된 KTDB Link",
        show=True,
    )

    for _, link in matched_links_wgs84.iterrows():

        popup_text = (
            f"<b>KTDB Link</b><br>"
            f"LINK_ID: {link['LINK_ID']}<br>"
            f"F_NODE: {link['F_NODE']}<br>"
            f"T_NODE: {link['T_NODE']}<br>"
            f"LENGTH: {link['LENGTH']} m<br>"
            f"ROAD_NAME: {link.get('ROAD_NAME', '')}"
        )

        folium.GeoJson(
            data=link.geometry.__geo_interface__,
            tooltip=f"LINK_ID: {link['LINK_ID']}",
            popup=folium.Popup(popup_text, max_width=350),
            style_function=lambda feature: {
                "weight": 6,
                "opacity": 0.85,
            },
        ).add_to(link_layer)

    link_layer.add_to(map_object)

    if shortest_path_df is not None and not shortest_path_df.empty:
        add_shortest_path_layer(
            map_object,
            shortest_path_df,
            link_gdf,
        )

    stop_layer = folium.FeatureGroup(
        name="BMS 정류장",
        show=True,
    )

    for _, stop in stop_wgs84.iterrows():

        representative_text = ""

        if "대표_NODE" in stop.index:
            representative_text = (
                f"대표 NODE: {stop['대표_NODE']}<br>"
                f"선택 구분: {stop['대표_NODE_구분']}<br>"
                f"대표 NODE 거리: {stop['대표_NODE거리_m']} m<br>"
            )

        popup_text = (
            f"<b>{stop['정류장명']}</b><br>"
            f"정류장순서: {stop['정류장순서']}<br>"
            f"정류장아이디: {stop['정류장아이디']}<br>"
            f"매칭 LINK_ID: {stop['LINK_ID']}<br>"
            f"F_NODE: {stop['F_NODE']}<br>"
            f"T_NODE: {stop['T_NODE']}<br>"
            f"{representative_text}"
            f"도로명: {stop['ROAD_NAME']}<br>"
            f"Link 거리: {stop['링크매칭거리_m']} m"
        )

        folium.Marker(
            location=[stop.geometry.y, stop.geometry.x],
            tooltip=f"{stop['정류장순서']}번 {stop['정류장명']}",
            popup=folium.Popup(popup_text, max_width=350),
            icon=folium.Icon(icon="bus", prefix="fa"),
        ).add_to(stop_layer)

    stop_layer.add_to(map_object)

    bounds = None

    if shortest_path_df is not None and not shortest_path_df.empty:
        bounds = get_shortest_path_bounds(
            shortest_path_df,
            link_gdf,
        )

    if bounds is not None:
        map_object.fit_bounds(bounds)
    else:
        min_x, min_y, max_x, max_y = matched_links_wgs84.total_bounds
        map_object.fit_bounds(
            [
                [min_y, min_x],
                [max_y, max_x],
            ]
        )

    folium.LayerControl().add_to(map_object)

    output_file = Path(output_path)
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    map_object.save(str(output_file))

    return str(output_file.resolve())