# Path: src/backend/langflow/services/database/models/flow/model.py

import re
import warnings
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

import emoji
from emoji import purely_emoji  # type: ignore
from fastapi import HTTPException, status
from pydantic import field_serializer, field_validator
from sqlalchemy import Text, UniqueConstraint
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from langflow.schema import Data
from langflow.services.database.models.vertex_builds.model import VertexBuildTable

if TYPE_CHECKING:
    from langflow.services.database.models import TransactionTable
    from langflow.services.database.models.folder import Folder
    from langflow.services.database.models.message import MessageTable
    from langflow.services.database.models.user import User


class FlowBase(SQLModel):
    name: str = Field(index=True)
    description: str | None = Field(default=None, sa_column=Column(Text, index=True, nullable=True))
    icon: str | None = Field(default=None, nullable=True)
    icon_bg_color: str | None = Field(default=None, nullable=True)
    data: dict | None = Field(default=None, nullable=True)
    is_component: bool | None = Field(default=False, nullable=True)
    updated_at: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=True)
    webhook: bool | None = Field(default=False, nullable=True, description="Can be used on the webhook endpoint")
    endpoint_name: str | None = Field(default=None, nullable=True, index=True)

    @field_validator("endpoint_name")
    @classmethod
    def validate_endpoint_name(cls, v):
        # Endpoint name must be a string containing only letters, numbers, hyphens, and underscores
        if v is not None:
            if not isinstance(v, str):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Endpoint name must be a string",
                )
            if not re.match(r"^[a-zA-Z0-9_-]+$", v):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Endpoint name must contain only letters, numbers, hyphens, and underscores",
                )
        return v

    @field_validator("icon_bg_color")
    def validate_icon_bg_color(cls, v):
        if v is not None and not isinstance(v, str):
            msg = "Icon background color must be a string"
            raise ValueError(msg)
        # validate that is is a hex color
        if v and not v.startswith("#"):
            msg = "Icon background color must start with #"
            raise ValueError(msg)

        # validate that it is a valid hex color
        if v and len(v) != 7:
            msg = "Icon background color must be 7 characters long"
            raise ValueError(msg)
        return v

    @field_validator("icon")
    def validate_icon_atr(cls, v):
        #   const emojiRegex = /\p{Emoji}/u;
        # const isEmoji = emojiRegex.test(data?.node?.icon!);
        # emoji pattern in Python
        if v is None:
            return v
        # we are going to use the emoji library to validate the emoji
        # emojis can be defined using the :emoji_name: syntax

        if not v.startswith(":") and not v.endswith(":"):
            return v
        elif not v.startswith(":") or not v.endswith(":"):
            # emoji should have both starting and ending colons
            # so if one of them is missing, we will raise
            msg = f"Invalid emoji. {v} is not a valid emoji."
            raise ValueError(msg)

        emoji_value = emoji.emojize(v, variant="emoji_type")
        if v == emoji_value:
            warnings.warn(f"Invalid emoji. {v} is not a valid emoji.")
            icon = v
        icon = emoji_value

        if purely_emoji(icon):
            # this is indeed an emoji
            return icon
        # otherwise it should be a valid lucide icon
        if v is not None and not isinstance(v, str):
            msg = "Icon must be a string"
            raise ValueError(msg)
        # is should be lowercase and contain only letters and hyphens
        if v and not v.islower():
            msg = "Icon must be lowercase"
            raise ValueError(msg)
        if v and not v.replace("-", "").isalpha():
            msg = "Icon must contain only letters and hyphens"
            raise ValueError(msg)
        return v

    @field_validator("data")
    def validate_json(v):
        if not v:
            return v
        if not isinstance(v, dict):
            msg = "Flow must be a valid JSON"
            raise ValueError(msg)

        # data must contain nodes and edges
        if "nodes" not in v.keys():
            msg = "Flow must have nodes"
            raise ValueError(msg)
        if "edges" not in v.keys():
            msg = "Flow must have edges"
            raise ValueError(msg)

        return v

    # updated_at can be serialized to JSON
    @field_serializer("updated_at")
    def serialize_datetime(value):
        if isinstance(value, datetime):
            # I'm getting 2024-05-29T17:57:17.631346
            # and I want 2024-05-29T17:57:17-05:00
            value = value.replace(microsecond=0)
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        return value

    @field_validator("updated_at", mode="before")
    def validate_dt(cls, v):
        if v is None:
            return v
        elif isinstance(v, datetime):
            return v

        return datetime.fromisoformat(v)


class Flow(FlowBase, table=True):  # type: ignore
    id: UUID = Field(default_factory=uuid4, primary_key=True, unique=True)
    data: dict | None = Field(default=None, sa_column=Column(JSON))
    user_id: UUID | None = Field(index=True, foreign_key="user.id", nullable=True)
    user: "User" = Relationship(back_populates="flows")
    folder_id: UUID | None = Field(default=None, foreign_key="folder.id", nullable=True, index=True)
    folder: Optional["Folder"] = Relationship(back_populates="flows")
    messages: list["MessageTable"] = Relationship(back_populates="flow")
    transactions: list["TransactionTable"] = Relationship(back_populates="flow")
    vertex_builds: list["VertexBuildTable"] = Relationship(back_populates="flow")

    def to_data(self):
        serialized = self.model_dump()
        data = {
            "id": serialized.pop("id"),
            "data": serialized.pop("data"),
            "name": serialized.pop("name"),
            "description": serialized.pop("description"),
            "updated_at": serialized.pop("updated_at"),
        }
        record = Data(data=data)
        return record

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="unique_flow_name"),
        UniqueConstraint("user_id", "endpoint_name", name="unique_flow_endpoint_name"),
    )


class FlowCreate(FlowBase):
    user_id: UUID | None = None
    folder_id: UUID | None = None


class FlowRead(FlowBase):
    id: UUID
    user_id: UUID | None = Field()
    folder_id: UUID | None = Field()


class FlowUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
    data: dict | None = None
    folder_id: UUID | None = None
    endpoint_name: str | None = None

    @field_validator("endpoint_name")
    @classmethod
    def validate_endpoint_name(cls, v):
        # Endpoint name must be a string containing only letters, numbers, hyphens, and underscores
        if v is not None:
            if not isinstance(v, str):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Endpoint name must be a string",
                )
            if not re.match(r"^[a-zA-Z0-9_-]+$", v):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Endpoint name must contain only letters, numbers, hyphens, and underscores",
                )
        return v
