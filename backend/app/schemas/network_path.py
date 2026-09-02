import uuid
from datetime import datetime

from pydantic import BaseModel


class NetworkHop(BaseModel):
    hop_number: int
    address: str | None
    avg_latency_ms: float | None
    packet_loss_percent: float | None


class NetworkPathSample(BaseModel):
    recorded_at: datetime
    target: str
    reachable: bool
    hops: list[NetworkHop]
    quality_score: int | None = None


class NetworkPathHistory(BaseModel):
    current: NetworkPathSample | None
    samples: list[NetworkPathSample]


class NetworkPathFleetRow(BaseModel):
    """One row per visible server in the fleet-wide network overview — reachable=None
    (with every other field also None) means no sample has ever arrived for this
    server (agent not yet updated to 1.4.0+, or just enrolled), distinct from
    reachable=False (a real sample that failed to reach the target)."""

    server_id: uuid.UUID
    hostname: str
    site_id: uuid.UUID | None
    site_name: str | None
    target: str | None
    reachable: bool | None
    hop_count: int | None
    final_latency_ms: float | None
    # Kept separate rather than one "max loss" number: loss at an intermediate router
    # is often benign (routers deprioritizing ICMP replies, not a real path problem —
    # see the caveat text on the network overview page), while loss at the destination
    # itself means the server genuinely isn't reachable. Merging them into one number
    # made it impossible to tell which case a técnico was looking at.
    destination_loss_percent: float | None
    intermediate_max_loss_percent: float | None
    quality_score: int | None
    recorded_at: datetime | None


class NetworkLatencySparklinePoint(BaseModel):
    recorded_at: datetime
    latency_ms: float | None


class NetworkLatencySparkline(BaseModel):
    server_id: uuid.UUID
    points: list[NetworkLatencySparklinePoint]
