import json


def build_extraction_prompt(text: str) -> str:
    expected_schema = {
        "name": "string or null",
        "account_number": "string or null",
    }

    instructions = f"""
You are an information extraction assistant.

Your task:
Extract the following fields from the provided text:
1. name
2. account_number

Rules:
- Return JSON only.
- Do not explain anything.
- Do not include markdown.
- If a field is missing, return null for that field.
- Prefer the main customer/account holder name if multiple names appear.
- Preserve the account number exactly as written if possible.
- Only return these keys: name, account_number

Expected JSON schema:
{json.dumps(expected_schema, indent=2)}

Text to analyze:
\"\"\"
{text}
\"\"\"
"""
    return instructions.strip()