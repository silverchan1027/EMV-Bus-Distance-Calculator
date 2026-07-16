from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
KTDB_DATA_DIR = DATA_DIR / "ktdb"

ROUTE_STOP_CSV = RAW_DATA_DIR / "경기도_BMS노선경유정류소정보.csv"
STOP_HISTORY_CSV = RAW_DATA_DIR / "경기도_BMS정류소이력정보.csv"
GIS_NODE_CSV = RAW_DATA_DIR / "경기도_BMSGIS정보(노드).csv"
GIS_LINK_CSV = RAW_DATA_DIR / "경기도_BMSGIS정보(링크).csv"

KTDB_DIR = KTDB_DATA_DIR / "[2026-07-01]NODELINKDATA"

KTDB_NODE = KTDB_DIR / "MOCT_NODE.shp"
KTDB_LINK = KTDB_DIR / "MOCT_LINK.shp"