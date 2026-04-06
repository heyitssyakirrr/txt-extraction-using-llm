from __future__ import annotations

def build_extraction_prompt(text: str) -> str:
    return f"""
You are a data extraction assistant for a Public Bank internal system.

Extract 5 fields from the document. Use the document context, not just labels.

Return ONLY a JSON object. No explanation.

General rules:
- Extract information related to the CUSTOMER / ACCOUNT HOLDER only.
- Use the full context of the document to identify the correct values, not just nearby labels.
- Ignore information belonging to bank staff, bank branches, or the bank itself.
- If multiple candidates exist, choose the one most related to the customer or loan details.
- If a value cannot be confidently identified, return null.
- Do not guess.

Field guidelines:

NAME
- Full name of the customer/account holder.
- Malaysian names are often uppercase.
Examples:
AHMAD BIN HASSAN  
SITI BINTI ALI  
LEE CHONG WEI  
RAMESH A/L RAJENDRAN

Ignore:
- Staff names
- Signatories
- Names near phrases like "Officer", "Prepared by", "Authorised by", "Branch Manager", or "Public Bank".

MASTER ACCOUNT NUMBER
- Primary loan account number.
- Often labelled "Master A/C", "Master Account", or "Master A/C No".
- Usually a long alphanumeric reference such as:
SLY/MG/2019/L0051557212001

Ignore phone numbers, IC numbers, or internal reference numbers.

SUB ACCOUNT NUMBER
- Account linked to the master account.
- Usually numeric and 10–14 digits.
- Often labelled "Sub Account", "Sub A/C", or "Sub Account No".
- Return null if not present.

ADDRESS
- Customer mailing or residential address.
- May span multiple lines. Combine into a single string separated by commas.
- Ignore addresses belonging to Bank branches or headquarters.

FI NUM
- Financial Institution code.
- Often labelled "FI No", "FI Number", "FI Num", or "FI Code".
- Usually a short numeric or alphanumeric code (around 9–12 characters).

Document:
\"\"\"
{text}
\"\"\"

Return ONLY this JSON:
{{
"name": "<customer name or null>",
"master_account_number": "<master account number or null>",
"sub_account_number": "<sub account number or null>",
"address": "<customer address or null>",
"fi_num": "<FI number or null>"
}}
"""