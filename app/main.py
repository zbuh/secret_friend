from fastapi import FastAPI
from decouple import config

from app.models import LotteryRequest, LotteryResponse
from app.utils import matchup, send_email

# MAIN APP
app = FastAPI(
    title="Secret Friend Lottery",
    version=1.0,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,
        "displayRequestDuration": True,
        "tryItOutEnabled": True,
    },
)


@app.post("/secret_friend", response_model=LotteryResponse, include_in_schema=True)
async def info(
    lottery_request: LotteryRequest, test_only: bool = True, token: str = None
):
    # CHECK FOR TOKEN AUTH
    if token != config("token", cast=str, default=""):
      return  LotteryResponse(status="UNAUTHORIZED")

    results = matchup(lottery_request.friends)

    if not test_only:  # SEND EMAIL, DONT SHOW RESULTS
        mail_status = send_email(
            results,
            title=lottery_request.title,
            budget=lottery_request.budget,
        )
        response = LotteryResponse(status="OK" if mail_status else "ERROR", result=None)

    else:  # ONLY FOR TEST, DONT SEND EMAIL
        response = LotteryResponse(
            status="TEST_ONLY",
            result=[{r[0].name: r[1].name} for r in results],
        )

    return response
