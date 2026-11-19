import psutil
from fastapi import APIRouter

router = APIRouter()


@router.get("/system/metrics")
def system_metrics() -> dict[str, float | int]:
    memory = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": memory.percent,
        "memory_used": memory.used,
        "memory_total": memory.total,
    }
