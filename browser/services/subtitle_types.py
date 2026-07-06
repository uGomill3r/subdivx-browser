from dataclasses import dataclass


@dataclass
class SubtitleResult:
    id: str
    title: str
    description: str
    uploader_name: str
    posted_at: str
    downloads: int
    matched_by: str  # criterio usado para encontrarlo


def to_subtitle_results(raw: list[dict], matched_by: str) -> list[SubtitleResult]:
    """Convierte resultados crudos (de cualquier proveedor) a dataclasses."""
    return [
        SubtitleResult(
            id=str(r.get("id", "")),
            title=r.get("title", ""),
            description=r.get("description", ""),
            uploader_name=r.get("uploader_name", ""),
            posted_at=r.get("posted_at", ""),
            downloads=r.get("downloads", 0),
            matched_by=matched_by,
        )
        for r in raw
    ]
