from typing import Optional, List, Dict, Tuple
from pydantic import BaseModel


class Person(BaseModel):
    name: str
    email: str


class LotteryRequest(BaseModel):
    friends: List[Person]
    title: str
    budget: str = "Max money to be spent"

    class Config:
        schema_extra = {
            "example": {
                "friends": [
                    {"name": "Friend 1", "email": "friend1@gmail.com"},
                    {"name": "Friend 2", "email": "friend2@gmail.com"},
                    {"name": "Friend 3", "email": "friend3@gmail.com"},
                ],
                "title": "Title of the event",
                "budget": "10 eur.",
            }
        }


class LotteryResponse(BaseModel):
    status: str
    result: Optional[List[Dict[str, str]]]

    class Config:
        schema_extra = {
            "example": {
                "status": "OK",
                "result": [
                    {"Friend 1": "Friend 2"},
                    {"Friend 2": "Friend 3"},
                    {"Friend 3": "Friend 1"},
                ],
            }
        }
