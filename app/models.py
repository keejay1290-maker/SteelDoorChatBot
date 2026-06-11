"""Pydantic request/response models for the SteelDoorAi API.

Modelled on Steel Door Company's real product line. door_set/door_type/mechanism
are the natural-language intake fields; product key is auto-derived in the engine.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

DoorSet = Literal["single", "double"]
DoorType = Literal["internal", "external", "fire_rated", "wine_room"]
Mechanism = Literal["hinged", "sliding", "concertina"]
Glass = Literal["clear", "reeded", "frosted", "bespoke"]
FireRating = Literal["none", "FD30", "FD60"]
Threshold = Literal["flush", "weathered", "step_over"]


class QuoteRequest(BaseModel):
    """A request for a bespoke steel door estimate. Dimensions in millimetres."""

    door_set: DoorSet = "single"
    door_type: DoorType = "internal"
    mechanism: Mechanism = "hinged"
    width_mm: float = Field(900, gt=0, le=6000, description="Overall opening width in mm")
    height_mm: float = Field(2100, gt=0, le=4000, description="Overall opening height in mm")
    glass: Glass = "clear"
    ral_colour: Optional[str] = Field(None, description="RAL colour code e.g. 'RAL 9005'")
    fire_rating: FireRating = "none"
    side_panels: int = Field(0, ge=0, le=4, description="Number of fixed side panels")
    threshold: Threshold = "flush"
    quantity: int = Field(1, ge=1, le=100)


class QuoteLine(BaseModel):
    label: str
    amount: float


class QuoteResponse(BaseModel):
    reference: str
    product_name: str
    currency: str = "GBP"
    lines: list[QuoteLine]
    unit_price: float
    quantity: int
    subtotal: float
    sale_discount: float
    vat: float
    total: float
    lead_time: str
    image_url: Optional[str] = None
    notes: list[str] = []


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    session_id: Optional[str] = None


class SessionState(BaseModel):
    """Partial session state returned to the client on each chat turn."""
    session_id: str
    stage: int = 1
    readiness_score: int = 0
    routing: Optional[str] = None
    internal_brief: Optional[str] = None
    # Collected fields (for UI progress display)
    has_name: bool = False
    has_email: bool = False
    has_phone: bool = False
    has_postcode: bool = False
    has_door_spec: bool = False
    has_dimensions: bool = False
    has_quantity: bool = False
    has_glass: bool = False
    missing_fields: list[str] = []


class ChatResponse(BaseModel):
    reply: str
    quote: Optional[QuoteResponse] = None
    session: Optional[SessionState] = None


class EnquiryRequest(BaseModel):
    """A customer enquiry / lead, optionally attached to an estimate."""

    name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)
    postcode: Optional[str] = Field(None, max_length=12)
    message: Optional[str] = Field(None, max_length=2000)
    quote_reference: Optional[str] = Field(None, max_length=20)
    quote_total: Optional[float] = None


class EnquiryResponse(BaseModel):
    id: int
    reference: str
    status: str = "received"
    message: str
