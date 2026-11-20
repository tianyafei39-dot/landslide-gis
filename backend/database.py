from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DB_PATH 可经环境变量覆盖（Docker 部署时指向挂载目录，解决 WAL 伴生文件挂载问题）；
# 默认仍为 backend/sql_app.db，本机开发行为不变
_db_path = os.getenv("DB_PATH") or os.path.join(BASE_DIR, "sql_app.db")
_db_dir = os.path.dirname(_db_path)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_db_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 5},  # busy_timeout=5s：并发写等待而非立刻报锁
)


@event.listens_for(engine, "connect")
def _enable_sqlite_wal(dbapi_connection, _record):
    """WAL 模式：读写不互斥，登录/查询突发并发下不再锁库"""
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()