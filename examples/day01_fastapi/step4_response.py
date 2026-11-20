"""4단계 — 응답 모델과 상태 코드

실행:
    uvicorn step4_response:app --reload

해 볼 것:
    start_time 을 넣어 저장한다 → 응답에는 없다. response_model 이 걸러 낸 것이다
    저장에 성공하면 200 이 아니라 201 이 온다
    서버를 다시 켜면 PLANS 가 빈다 (지금은 메모리)
"""
from datetime import date

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

