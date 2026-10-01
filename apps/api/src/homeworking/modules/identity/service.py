"""Identity port and the Phase I adapter: cookie-session guest accounts.

Guests get an account on first use so projects are saved without sign-up. A later OIDC adapter
(e.g. Zitadel) implements the same port and can upgrade guest accounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from homeworking.db.schema import UserRow


@dataclass(frozen=True)
class User:
    id: UUID
    is_guest: bool
    display_name: str | None = None


class IdentityProvider(Protocol):
    async def get(self, user_id: UUID) -> User | None: ...

    async def create_guest(self) -> User: ...


class SqlGuestIdentityProvider:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, user_id: UUID) -> User | None:
        async with self._sessions() as session:
            row = await session.get(UserRow, user_id)
            if row is None:
                return None
            return User(id=row.id, is_guest=row.is_guest, display_name=row.display_name)

    async def create_guest(self) -> User:
        user = User(id=uuid4(), is_guest=True)
        async with self._sessions.begin() as session:
            session.add(UserRow(id=user.id, is_guest=True))
        return user
