"""코디 플랜 재계획 요청 스키마."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReplanRequest(BaseModel):
    """기존 코디 플랜의 검색 조건 변경 요청."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(
        default="local",
        min_length=1,
        max_length=100,
    )

    message: str | None = Field(
        default=None,
        max_length=1000,
        description="자연어 조건 변경 요청",
    )

    keyword: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    brand: str | None = Field(default=None, max_length=100)

    gender: Literal["all", "men", "women"] | None = None

    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)

    color: str | None = Field(default=None, max_length=50)
    size: str | None = Field(default=None, max_length=50)

    sort: Literal[
        "popular",
        "new",
        "discount",
        "price_asc",
        "price_desc",
        "reviews",
        "sales",
        "sales_day",
        "sales_week",
        "sales_month",
        "sales_3months",
        "sales_year",
    ] | None = None

    limit: int | None = Field(default=None, ge=1, le=100)

    exclude_product_ids: list[str | int] = Field(
        default_factory=list,
        max_length=50,
    )
