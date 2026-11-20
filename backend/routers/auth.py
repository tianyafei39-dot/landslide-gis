from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db
from db_models import User
from security import verify_password, create_access_token, get_current_user, hash_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginBody(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(body: LoginBody, db=Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="账号已禁用")
    
    token = create_access_token(user.id, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }

@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}

# 注册请求体模型
class RegisterBody(BaseModel):
    username: str
    password: str

# 注册接口
@router.post("/register")
def register(body: RegisterBody, db=Depends(get_db)):
    # 1. 校验用户名是否已存在
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="该用户名已被注册")
    
    # 2. 限制用户名长度
    if len(body.username) < 3 or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="用户名至少3位，密码至少6位")
    
    # 3. 创建普通用户 (role="user")
    new_user = User(
        username=body.username,
        password_hash=hash_password(body.password), # 密码加密
        role="user",
        is_active=True
    )
    db.add(new_user)
    db.commit()
    
    return {"msg": "注册成功，请登录"}