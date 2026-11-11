"""Tool schemas — what the LLM sees."""

SET_ICP = {
    "name": "signaldesk_set_icp",
    "description": (
        "Create or update the user's Ideal Customer Profile used to score hiring and launch leads. "
        "Pass only fields you want to change. Keywords, roles, stack, locations, company_stage, "
        "and exclusions can be lists or comma-separated strings."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keywords": {"type": "string", "description": "Comma-separated ICP keywords (e.g. 'AI agents, developer tools')."},
            "roles": {"type": "string", "description": "Roles to look for in hiring signals."},
            "stack": {"type": "string", "description": "Tech stack keywords."},
            "locations": {"type": "string", "description": "Preferred locations."},
            "remote_ok": {"type": "boolean"},
            "onsite_ok": {"type": "boolean"},
            "company_stage": {"type": "string", "description": "e.g. seed, early, growth"},
            "exclusions": {"type": "string", "description": "Terms that should lower the score."},
            "offer": {"type": "string", "description": "One-sentence description of what the user sells."},
            "booking_link": {"type": "string", "description": "Optional public booking URL to include in drafts."},
            "sender_name": {"type": "string"},
            "qualify_min_score": {"type": "integer", "description": "Minimum score to mark a lead qualified (default 35)."},
            "followup_days": {"type": "integer"},
        },
    },
}

SCAN = {
    "name": "signaldesk_scan",
    "description": (
        "Scan public hiring and/or launch sources, score new leads against the ICP, and upsert them. "
        "Does not send any outreach. kind can be 'all', 'hiring', 'launches', or a source id "
        "(hn_hiring, yc_hiring, hn_show, yc_launches)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": "all | hiring | launches | hn_hiring | yc_hiring | hn_show | yc_launches",
                "default": "all",
            },
        },
    },
}

LIST = {
    "name": "signaldesk_list",
    "description": "List stored leads, optionally filtered by stage or signal_type, highest score first.",
    "parameters": {
        "type": "object",
        "properties": {
            "stage": {"type": "string", "description": "new|qualified|drafted|approved|sent|replied|won|lost"},
            "signal_type": {"type": "string", "description": "hiring or launch"},
            "limit": {"type": "integer", "default": 25},
        },
    },
}

DRAFT = {
    "name": "signaldesk_draft",
    "description": (
        "Write an outreach draft for a lead and move it to 'drafted'. "
        "Uses the host LLM when available, otherwise a template. Never sends."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "lead_id": {"type": "string", "description": "Lead id (sd-...)."},
        },
        "required": ["lead_id"],
    },
}

APPROVE = {
    "name": "signaldesk_approve",
    "description": (
        "Mark a drafted (or qualified) lead as approved for outreach. "
        "This is the in-plugin approval gate. It does not send a message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "lead_id": {"type": "string"},
        },
        "required": ["lead_id"],
    },
}

MARK = {
    "name": "signaldesk_mark",
    "description": "Update a lead's stage or notes after a human has acted (sent, replied, won, lost).",
    "parameters": {
        "type": "object",
        "properties": {
            "lead_id": {"type": "string"},
            "stage": {"type": "string", "description": "sent|replied|won|lost (also allowed: qualified|drafted|approved)."},
            "notes": {"type": "string"},
        },
        "required": ["lead_id"],
    },
}

FOLLOWUPS = {
    "name": "signaldesk_followups",
    "description": "List sent leads that are due for a follow-up based on the ICP followup_days setting.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 20},
        },
    },
}

EXPORT = {
    "name": "signaldesk_export_csv",
    "description": "Export leads to a CSV file under the plugin data directory. Never includes secrets.",
    "parameters": {
        "type": "object",
        "properties": {
            "stage": {"type": "string"},
            "signal_type": {"type": "string"},
        },
    },
}

SOURCES = {
    "name": "signaldesk_sources",
    "description": "List available signal sources, whether they are enabled, and their rate-limit notes.",
    "parameters": {"type": "object", "properties": {}},
}

PREPARE_SEND = {
    "name": "signaldesk_prepare_send",
    "description": (
        "For an approved lead, write a local .eml file and return a mailto: link plus the draft body "
        "to copy. This does not transmit email and will refuse unless the lead is approved."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "lead_id": {"type": "string"},
        },
        "required": ["lead_id"],
    },
}

BOARD = {
    "name": "signaldesk_board",
    "description": "Regenerate the standalone HTML pipeline board and return its file path.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Optional destination path. Defaults to the plugin data dir."},
        },
    },
}

ALL_SCHEMAS = [SET_ICP, SCAN, LIST, DRAFT, APPROVE, MARK, FOLLOWUPS, EXPORT, SOURCES, PREPARE_SEND, BOARD]
