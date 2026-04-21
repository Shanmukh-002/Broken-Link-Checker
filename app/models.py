from pydantic import BaseModel, Field


class LinkResult(BaseModel):
    source_url: str = Field(..., description="Page where the link was found")
    target_url: str = Field(..., description="Resolved URL being checked")
    anchor_text: str = Field(default="", description="Text inside the anchor tag")
    status_code: int | None = Field(default=None, description="HTTP status code")
    is_broken: bool = Field(..., description="Whether the link is broken")
    is_blocked: bool = Field(
        default=False,
        description="Whether the link appears blocked (403/401/429) rather than broken",
    )
    error: str | None = Field(default=None, description="Error details if request failed")
    is_internal: bool = Field(..., description="Whether the link belongs to the same domain")
    response_time_ms: float | None = Field(default=None, description="Response time in milliseconds")
