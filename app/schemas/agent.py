"""Fashion Agent 실행 요청 스키마."""

from pydantic import BaseModel, ConfigDict, Field


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        min_length=1,
        max_length=4000,
        description="사용자의 자연어 코디 요청",
    )

    user_id: str = Field(
        default="local",
        min_length=1,
        max_length=100,
        description="플랜 저장에 사용할 사용자 구분 ID",
    )
