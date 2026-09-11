"""Typed, provider-neutral identity claims used by authorization and audit code."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class AuthenticatedPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=255)
    roles: frozenset[Role] = Field(min_length=1)
    issuer: str = Field(min_length=1, max_length=255)

    def can_review(self) -> bool:
        return bool(self.roles & {Role.REVIEWER, Role.ADMIN})

    @property
    def audit_role(self) -> Role:
        if Role.ADMIN in self.roles:
            return Role.ADMIN
        if Role.REVIEWER in self.roles:
            return Role.REVIEWER
        return Role.ANALYST
