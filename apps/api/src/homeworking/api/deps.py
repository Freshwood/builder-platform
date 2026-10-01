"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from homeworking.bootstrap import Container
from homeworking.modules.identity.service import User

SESSION_USER_KEY = "uid"


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def current_user(request: Request, container: ContainerDep) -> User:
    """Return the session user; create a guest account on first use."""
    raw = request.session.get(SESSION_USER_KEY)
    if raw:
        try:
            user = await container.identity.get(UUID(raw))
        except ValueError:
            user = None
        if user is not None:
            return user
    user = await container.identity.create_guest()
    request.session[SESSION_USER_KEY] = str(user.id)
    return user


UserDep = Annotated[User, Depends(current_user)]
