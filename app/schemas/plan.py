"""코디 플랜 요청 및 응답 스키마."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PlanStatus = Literal["draft", "planned", "completed", "archived"]


class PlanProduct(BaseModel):
    """코디 플랜에 저장할 상품 정보."""

    model_config = ConfigDict(extra="allow")

    product_id: int | str
    name: str | None = None
    brand_name: str | None = None
    sale_price: int | None = Field(default=None, ge=0)
    product_url: str | None = None


class PlanCreate(BaseModel):
    """코디 플랜 생성 요청."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="local", min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    occasion: str | None = Field(default=None, max_length=100)
    season: str | None = Field(default=None, max_length=50)
    budget: int | None = Field(default=None, ge=0)
    products: list[PlanProduct] = Field(default_factory=list, max_length=50)
    status: PlanStatus = "draft"


class PlanUpdate(BaseModel):
    """코디 플랜 부분 수정 요청."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    occasion: str | None = Field(default=None, max_length=100)
    season: str | None = Field(default=None, max_length=50)
    budget: int | None = Field(default=None, ge=0)
    products: list[PlanProduct] | None = Field(default=None, max_length=50)
    status: PlanStatus | None = None


class PlanRead(BaseModel):
    """코디 플랜 응답."""

    id: int
    user_id: str
    title: str
    description: str | None
    occasion: str | None
    season: str | None
    budget: int | None
    products: list[PlanProduct]
    status: PlanStatus
    created_at: str
    updated_at: str


class PlanListResponse(BaseModel):
    """코디 플랜 목록 응답."""

    items: list[PlanRead]
    total: int
    limit: int
    offset: int
