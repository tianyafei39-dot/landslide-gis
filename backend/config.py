import os
from dotenv import load_dotenv
load_dotenv()

# 然后加上这些变量
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET 未配置，请在 .env 中配置")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123456")
SIGN_SECRET = os.getenv("SIGN_SECRET") or JWT_SECRET
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
# 训练并发闸门：同时最多几个训练任务真正在跑，其余排队（建议 1~4）
TRAIN_MAX_CONCURRENT = int(os.getenv("TRAIN_MAX_CONCURRENT", "2"))
# 单个训练可用 CPU 核数：并发训练均分，避免互相抢核导致全体变慢
TRAIN_N_JOBS = max(1, (os.cpu_count() or 2) // max(1, TRAIN_MAX_CONCURRENT))