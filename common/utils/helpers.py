"""
Helper registry: maps helper IDs to metadata, and groups to accessible helpers.
"""

from __future__ import annotations

HELPER_CODES: dict[str, str] = {
    "01": "policy_helper",
    "02": "db-helper",
    "03": "odd-helper",
    "04": "file-reader",
}

GROUP_HELPER_ACCESS: dict[str, list[str]] = {
    "general": ["policy_helper"],
}

HELPERS: list[dict] = [
    {
        "id": "policy_helper",
        "name": "Policy Helper",
        "description": "Ask questions about company policies",
        "url": "/policy_helper",
        "implemented": True,
    },
    # DO NOT DELETE THIS COMMENTED OUT CODE. IT IS FOR FUTURE IMPLEMENTATION OF NEW HELPERS.
    # {
    #     "id": "db-helper",
    #     "name": "DB Helper",
    #     "description": "Natural language database queries",
    #     "url": "/db-helper",
    #     "implemented": False,
    # },
    # {
    #     "id": "odd-helper",
    #     "name": "ODD Helper",
    #     "description": "ODD workflow assistant",
    #     "url": "/odd-helper",
    #     "implemented": False,
    # },
    # {
    #     "id": "file-reader",
    #     "name": "File Reader",
    #     "description": "Intelligent document reader",
    #     "url": "/file-reader",
    #     "implemented": False,
    # },
]
