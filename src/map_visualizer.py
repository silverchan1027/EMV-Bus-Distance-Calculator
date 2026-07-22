from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString
from shapely.ops import substring

from path_visualizer import (
    add_shortest_path_layer,
    get_shortest_path_bounds,
)


def _find_stop_row_by_name(stop_df: pd.DataFrame, stop_name: str) -> pd.Series:
    matches = stop_df[stop_df["정류장명"].astype(str) == str(stop_name)]
    if matches.empty:
        raise ValueError(f"지도 표시용 정류장 정보를 찾지 못했습니다: {stop_name}")
    return matches.iloc[0]


def _extract_projection_to_node_segment(
    link_geometry,
    projection_ratio: float,
    selected_node_type: str,
):
    if link_geometry is None or link_geometry.is_empty:
        return None

    geometry_length = float(link_geometry.length)
    if geometry_length <= 0:
        return None

    ratio = min(max(float(projection_ratio), 0.0), 1.0)
    projection_distance = geometry_length * ratio

    if selected_node_type == "F_NODE":
        segment = substring(link_geometry, 0.0, projection_distance)
    elif selected_node_type == "T_NODE":
        segment = substring(link_geometry, projection_distance, geometry_length)
    else:
        return None

    if segment is None or segment.is_empty or not isinstance(segment, LineString):
        return None

    return segment


def _add_projection_layers(
    map_object: folium.Map,
    stop_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
    shortest_path_df: pd.DataFrame | None,
) -> None:
    required = [
        "정류장순서", "정류장명", "KTDB_X", "KTDB_Y",
        "투영점_X", "투영점_Y", "투영점_비율", "LINK_ID",
        "LINK_GEOMETRY", "F_NODE방향_부분거리_m",
        "T_NODE방향_부분거리_m", "링크매칭거리_m",
    ]

    if any(column not in stop_df.columns for column in required):
        return

    stop_points = gpd.GeoDataFrame(
        stop_df.copy(),
        geometry=gpd.points_from_xy(stop_df["KTDB_X"], stop_df["KTDB_Y"]),
        crs=link_gdf.crs,
    ).to_crs(epsg=4326)

    projection_points = gpd.GeoDataFrame(
        stop_df.copy(),
        geometry=gpd.points_from_xy(stop_df["투영점_X"], stop_df["투영점_Y"]),
        crs=link_gdf.crs,
    ).to_crs(epsg=4326)

    projection_layer = folium.FeatureGroup(name="정류장 Link 투영점", show=True)
    connector_layer = folium.FeatureGroup(name="정류장-투영점 연결선", show=True)

    for index in range(len(stop_points)):
        stop_row = stop_points.iloc[index]
        projection_row = projection_points.iloc[index]

        popup_text = (
            f"<b>{projection_row['정류장명']} 투영점</b><br>"
            f"정류장순서: {projection_row['정류장순서']}<br>"
            f"LINK_ID: {projection_row['LINK_ID']}<br>"
            f"투영점 비율: {projection_row['투영점_비율']}<br>"
            f"F_NODE 방향 부분거리: {projection_row['F_NODE방향_부분거리_m']} m<br>"
            f"T_NODE 방향 부분거리: {projection_row['T_NODE방향_부분거리_m']} m<br>"
            f"정류장-도로 거리: {projection_row['링크매칭거리_m']} m"
        )

        folium.CircleMarker(
            location=[projection_row.geometry.y, projection_row.geometry.x],
            radius=7,
            tooltip=f"{projection_row['정류장순서']}번 {projection_row['정류장명']} 투영점",
            popup=folium.Popup(popup_text, max_width=380),
            color="red",
            fill=True,
            fill_opacity=1.0,
        ).add_to(projection_layer)

        folium.PolyLine(
            locations=[
                [stop_row.geometry.y, stop_row.geometry.x],
                [projection_row.geometry.y, projection_row.geometry.x],
            ],
            tooltip=(
                f"{projection_row['정류장명']} 정류장→도로 투영 거리 "
                f"{projection_row['링크매칭거리_m']}m"
            ),
            color="gray",
            weight=3,
            opacity=0.85,
            dash_array="6, 6",
        ).add_to(connector_layer)

    projection_layer.add_to(map_object)
    connector_layer.add_to(map_object)

    if shortest_path_df is None or shortest_path_df.empty:
        return

    path_required = [
        "출발정류장", "도착정류장",
        "출발접속NODE구분", "도착접속NODE구분",
    ]
    if any(column not in shortest_path_df.columns for column in path_required):
        return

    partial_layer = folium.FeatureGroup(name="투영점-선택 NODE 부분경로", show=True)

    for _, path_row in shortest_path_df.iterrows():
        if path_row.get("경로유형") == "동일_LINK_내부거리":
            continue

        start_stop = _find_stop_row_by_name(stop_df, path_row["출발정류장"])
        end_stop = _find_stop_row_by_name(stop_df, path_row["도착정류장"])

        sections = [
            (
                "출발", start_stop, path_row["출발접속NODE구분"],
                path_row.get("출발접속NODE"), path_row.get("출발부분거리(m)"),
            ),
            (
                "도착", end_stop, path_row["도착접속NODE구분"],
                path_row.get("도착접속NODE"), path_row.get("도착부분거리(m)"),
            ),
        ]

        for section_type, stop_row, node_type, node_id, partial_distance in sections:
            segment = _extract_projection_to_node_segment(
                stop_row["LINK_GEOMETRY"],
                stop_row["투영점_비율"],
                node_type,
            )
            if segment is None:
                continue

            segment_gdf = gpd.GeoDataFrame(
                [{"geometry": segment}],
                geometry="geometry",
                crs=link_gdf.crs,
            ).to_crs(epsg=4326)

            segment_geometry = segment_gdf.iloc[0].geometry
            popup_text = (
                f"<b>{section_type} Link 내부 부분경로</b><br>"
                f"구간: {path_row['출발정류장']} → {path_row['도착정류장']}<br>"
                f"정류장: {stop_row['정류장명']}<br>"
                f"LINK_ID: {stop_row['LINK_ID']}<br>"
                f"선택 NODE 구분: {node_type}<br>"
                f"선택 NODE: {node_id}<br>"
                f"부분거리: {partial_distance} m"
            )

            folium.GeoJson(
                data=segment_geometry.__geo_interface__,
                tooltip=f"{stop_row['정류장명']} 투영점→{node_type} {partial_distance}m",
                popup=folium.Popup(popup_text, max_width=380),
                style_function=lambda feature: {
                    "color": "orange",
                    "weight": 10,
                    "opacity": 0.95,
                },
            ).add_to(partial_layer)

    partial_layer.add_to(map_object)


def create_link_matching_map(
    nearest_link_df: pd.DataFrame,
    link_gdf: gpd.GeoDataFrame,
    node_gdf: gpd.GeoDataFrame | None = None,
    shortest_path_df: pd.DataFrame | None = None,
    output_path: str = "output/link_matching_map.html",
) -> str:
    """정류장, 매칭 Link, 투영점, 부분경로, Dijkstra 경로를 지도에 표시한다."""

    if nearest_link_df.empty:
        raise ValueError("지도에 표시할 최근접 Link 결과가 없습니다.")
    if link_gdf.empty:
        raise ValueError("KTDB Link 데이터가 비어 있습니다.")
    if link_gdf.crs is None:
        raise ValueError("KTDB Link 좌표계 정보가 없습니다.")

    required_columns = [
        "정류장순서", "정류장아이디", "정류장명", "KTDB_X", "KTDB_Y",
        "LINK_ID", "F_NODE", "T_NODE", "LENGTH", "ROAD_NAME", "링크매칭거리_m",
    ]
    missing_columns = [
        column for column in required_columns
        if column not in nearest_link_df.columns
    ]
    if missing_columns:
        raise KeyError(f"최근접 Link 결과에 필요한 컬럼이 없습니다: {missing_columns}")

    stop_gdf = gpd.GeoDataFrame(
        nearest_link_df.copy(),
        geometry=gpd.points_from_xy(nearest_link_df["KTDB_X"], nearest_link_df["KTDB_Y"]),
        crs=link_gdf.crs,
    )
    stop_wgs84 = stop_gdf.to_crs(epsg=4326)

    target_link_ids = set(nearest_link_df["LINK_ID"].dropna().astype(str))
    matched_links = link_gdf[
        link_gdf["LINK_ID"].astype(str).isin(target_link_ids)
    ].copy()
    if matched_links.empty:
        raise ValueError("매칭된 KTDB Link geometry를 찾지 못했습니다.")

    matched_links_wgs84 = matched_links.to_crs(epsg=4326)

    map_object = folium.Map(
        location=[stop_wgs84.geometry.y.mean(), stop_wgs84.geometry.x.mean()],
        zoom_start=16,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    link_layer = folium.FeatureGroup(name="매칭된 KTDB Link", show=True)
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
                "color": "black",
                "weight": 6,
                "opacity": 0.75,
            },
        ).add_to(link_layer)
    link_layer.add_to(map_object)

    _add_projection_layers(
        map_object,
        nearest_link_df,
        link_gdf,
        shortest_path_df,
    )

    if shortest_path_df is not None and not shortest_path_df.empty:
        add_shortest_path_layer(map_object, shortest_path_df, link_gdf)

    stop_layer = folium.FeatureGroup(name="BMS 정류장", show=True)
    for _, stop in stop_wgs84.iterrows():
        representative_text = ""
        if "대표_NODE" in stop.index:
            representative_text = (
                f"대표 NODE: {stop['대표_NODE']}<br>"
                f"선택 구분: {stop['대표_NODE_구분']}<br>"
                f"대표 NODE 거리: {stop['대표_NODE거리_m']} m<br>"
            )

        projection_text = ""
        if "투영점_X" in stop.index:
            projection_text = (
                f"투영점 비율: {stop['투영점_비율']}<br>"
                f"F_NODE 방향 부분거리: {stop['F_NODE방향_부분거리_m']} m<br>"
                f"T_NODE 방향 부분거리: {stop['T_NODE방향_부분거리_m']} m<br>"
            )

        popup_text = (
            f"<b>{stop['정류장명']}</b><br>"
            f"정류장순서: {stop['정류장순서']}<br>"
            f"정류장아이디: {stop['정류장아이디']}<br>"
            f"매칭 LINK_ID: {stop['LINK_ID']}<br>"
            f"F_NODE: {stop['F_NODE']}<br>"
            f"T_NODE: {stop['T_NODE']}<br>"
            f"{projection_text}{representative_text}"
            f"도로명: {stop['ROAD_NAME']}<br>"
            f"Link 매칭 거리: {stop['링크매칭거리_m']} m"
        )

        folium.Marker(
            location=[stop.geometry.y, stop.geometry.x],
            tooltip=f"{stop['정류장순서']}번 {stop['정류장명']}",
            popup=folium.Popup(popup_text, max_width=380),
            icon=folium.Icon(icon="bus", prefix="fa", color="blue"),
        ).add_to(stop_layer)
    stop_layer.add_to(map_object)

    bounds = None
    if shortest_path_df is not None and not shortest_path_df.empty:
        bounds = get_shortest_path_bounds(shortest_path_df, link_gdf)

    if bounds is not None:
        map_object.fit_bounds(bounds)
    else:
        min_x, min_y, max_x, max_y = matched_links_wgs84.total_bounds
        map_object.fit_bounds([[min_y, min_x], [max_y, max_x]])

    folium.LayerControl().add_to(map_object)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    map_object.save(str(output_file))

    return str(output_file.resolve())