from pathlib import Path
import geopandas as gpd
from scipy.spatial import cKDTree
import pandas as pd
from config import KTDB_NODE, KTDB_LINK

from config import (
    GIS_LINK_CSV,
    GIS_NODE_CSV,
    ROUTE_STOP_CSV,
    STOP_HISTORY_CSV,
)


def read_csv_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {path}")

    encodings = ["utf-8-sig", "cp949", "euc-kr"]

    for encoding in encodings:
        try:
            df = pd.read_csv(
                path,
                encoding=encoding,
                low_memory=False,
            )

            print(f"[성공] {path.name}")
            print(f"인코딩: {encoding}")
            print(f"행: {len(df):,}, 열: {len(df.columns)}")

            return df

        except UnicodeDecodeError:
            continue

    raise UnicodeError(f"인코딩을 확인할 수 없습니다: {path}")


def load_bms_data() -> dict[str, pd.DataFrame]:
    return {
        "route_stop": read_csv_file(ROUTE_STOP_CSV),
        "stop_history": read_csv_file(STOP_HISTORY_CSV),
        "gis_node": read_csv_file(GIS_NODE_CSV),
        "gis_link": read_csv_file(GIS_LINK_CSV),
    }




def load_ktdb_data():

    node = gpd.read_file(KTDB_NODE)

    link = gpd.read_file(KTDB_LINK)

    print("\nKTDB Node")
    print(node.shape)

    print("KTDB Link")
    print(link.shape)

    # ==========================
    # 샘플 출력
    # ==========================
    print("\n========== NODE SAMPLE ==========")
    print(node[["NODE_ID", "NODE_NAME", "geometry"]].head(10))

    print("\n========== LINK SAMPLE ==========")
    print(link[["LINK_ID", "F_NODE", "T_NODE", "geometry"]].head(10))

    return node, link

