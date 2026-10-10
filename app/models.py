from pydantic import BaseModel, Field, field_validator


class Person(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(default="", max_length=200)
    group: str = Field(default="", max_length=80)
    manager: bool = False

    @field_validator("name", "email", "group")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class EventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    budget: str = Field(default="", max_length=60)
    event_date: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    event_time: str = Field(default="", pattern=r"^(([01]\d|2[0-3]):[0-5]\d)?$")
    message: str = Field(default="", max_length=1000)
    participants: list[Person] = Field(min_length=3, max_length=200)


class LoginRequest(BaseModel):
    password: str = Field(max_length=200)


class ClaimRequest(BaseModel):
    participant_id: int
    pin: str = Field(pattern=r"^\d{4}$")


class EmailRequest(BaseModel):
    ids: list[int] | None = None  # None = everyone with an email who wasn't emailed yet
