"""认证接口：注册 / 登录 / 获取当前用户 / 修改密码。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from ..database import get_db
from ..models.user import User
from ..schemas.auth import ChangePasswordIn, LoginIn, RegisterIn, TokenOut
from ..schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == data.username).first()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    # 归还连接：bcrypt 计算约 250ms，不应在这段时间占着连接池
    db.close()

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 先取出需要的数据，随即归还连接：bcrypt 校验约 250ms，
    # 高并发登录时正是这段持续持有把连接池拖垮的。
    user_out = UserOut.model_validate(user)
    password_hash = user.password_hash
    db.close()

    if not verify_password(data.password, password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user_out.username)
    return TokenOut(access_token=token, user=user_out)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password")
def change_password(
    data: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"detail": "密码修改成功"}
