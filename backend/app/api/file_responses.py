def binary_responses(media_type: str, description: str) -> dict[int | str, dict[str, object]]:
    return {
        200: {
            "description": description,
            "content": {
                media_type: {
                    "schema": {"type": "string", "format": "binary"},
                }
            },
        }
    }


CSV_RESPONSES = binary_responses("text/csv", "CSV download")
XLSX_RESPONSES = binary_responses(
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "Excel workbook",
)
PDF_RESPONSES = binary_responses("application/pdf", "PDF download")
ICS_RESPONSES = binary_responses("text/calendar", "iCalendar download")

FILE_MEDIA_TYPES = frozenset(
    {
        "text/csv",
        "text/calendar",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)
