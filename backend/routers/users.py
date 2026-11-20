from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from database import get_db
from db_models import User
from security import hash_password, require_admin

router = APIRouter(prefix="/api/users", tags=["users"])

class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str = "user"

@router.get("")
def list_users(db=Depends(get_db), _: User = Depends(require_admin)):
    users = db.query(User).order_by(User.id).all()
    return [{"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active} for u in users]

@router.post("")
def create_user(body: CreateUserBody, db=Depends(get_db), _: User = Depends(require_admin)):
    if body.role not in ("admin", "user"):
        raise HTTPException(400, detail="角色只能是 admin 或 user")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, detail="用户名已存在")
    u = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active}

    # 在 routers/users.py 的末尾追加以下代码

class UpdateUserBody(BaseModel):
    role: str

@router.patch("/{user_id}")
def update_user_role(
    user_id: int, 
    body: UpdateUserBody, 
    db=Depends(get_db), 
    current_admin: User = Depends(require_admin) # 只有 admin 才能操作
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色，以防失去管理权限")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 user")
        
    user.role = body.role
    db.commit()
    return {"msg": "角色修改成功"}

@router.delete("/{user_id}")
def delete_user(
    user_id: int, 
    db=Depends(get_db), 
    current_admin: User = Depends(require_admin) # 只有 admin 才能操作
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
        
    db.delete(user)
    db.commit()
    return {"msg": "用户删除成功"}