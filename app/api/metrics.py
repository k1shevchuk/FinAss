from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

router = APIRouter(tags=["metrics"])

telegram_updates_total = Counter("telegram_updates_total", "Total Telegram updates")
telegram_commands_total = Counter("telegram_commands_total", "Telegram commands count", ["command"])
rate_limit_hits_total = Counter("rate_limit_hits_total", "Rate limit hits")
sheets_append_total = Counter("sheets_append_total", "Sheets append operations", ["status"])
sheets_append_latency_seconds = Histogram("sheets_append_latency_seconds", "Sheets append latency")
qr_decode_total = Counter("qr_decode_total", "QR decode operations", ["status"])
qr_decode_latency_seconds = Histogram("qr_decode_latency_seconds", "QR decode latency")
report_generation_seconds = Histogram("report_generation_seconds", "Report generation latency")


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
