from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical bank name list — exactly as they appear in the reference CSV.
# The LLM is instructed to pick from this list when possible.
# ---------------------------------------------------------------------------
_KNOWN_BANKS = """\
- BSN (Bank Simpanan Nasional)
- CIMB Bank
- CIMB Islamic
- Maybank
- Maybank Islamic
- Alliance Bank
- Alliance Islamic Bank
- Hong Leong Bank
- Hong Leong Islamic Bank
- RHB Bank
- RHB Islamic Bank
- AmBank
- AmBank Islamic
- HSBC Bank
- HSBC Amanah
- OCBC Bank
- OCBC Al-Amin
- Public Bank Berhad
- Public Islamic Bank
- Kuwait Finance House
- Standard Chartered Bank
- Standard Chartered Saadiq
- Bank Islam
- Bank Muamalat
- Affin Bank
- Affin Islamic Bank
- Agro Bank
- Bank Rakyat
- UOB Bank
- Citibank"""


def build_extraction_prompt(text: str) -> str:
    """Prompt for customer detail extraction."""
    return f"""\
You are a data extraction assistant for a Malaysian bank's internal system.
Your task is to extract exactly six fields from a bank document.

=== RULES ===
0. You are in JSON-only mode. Your entire response must be a single JSON object. Stop immediately after the closing brace. No introduction, no explanation, no conclusion.
1. The document may or may not have labels. Do NOT rely only on labels.
2. Use the full context of the document to determine the correct values.
3. Return ONLY a raw JSON object — no markdown, no code blocks, no explanation.
4. Do NOT repeat or explain the fields. Output the JSON object and nothing else.

=== HOW TO IDENTIFY EACH FIELD ===

NAME:
- Full name of the account holder, NOT a staff name, branch name, or bank name.
- Malaysian names are typically in FULL CAPITAL LETTERS.
- Common formats:
    - Malay  : AHMAD BIN HASSAN, SITI BINTI ALI
    - Chinese: LEE CHONG WEI, TAN AH KOW
    - Indian : RAMESH A/L RAJENDRAN, KAVITHA A/P SUBRAMANIAM
- Ignore names that are clearly a bank branch, company, or staff member.

MASTER ACCOUNT NUMBER:
- The primary account number, typically 10-16 digits, sometimes with dashes.
- Usually the main/parent account identifier.
- NOT a phone number, IC number, reference number, staff ID, or branch code.

SUB ACCOUNT NUMBER:
- A secondary account number linked to the master account.
- May be shorter than the master account number.
- Return null if not present.

ADDRESS:
- The customer's mailing or residential address.
- May span multiple lines — combine into one string separated by commas.
- Ignore bank branch addresses or addresses belonging to law firms / third parties.

FI NUM:
- Financial Institution number.
- Typically a 9-digit numeric code identifying the bank/branch.
- Usually started with digit 0 for most of the bank and sometimes can be starting with digit 3 for some banks like BSN and Bank Rakyat.
- May be labelled as "FI Code" or similar.

BANK NAME — READ THIS CAREFULLY:
- This document is a letter SENT BY Public Bank Berhad / Public Islamic Bank TO a customer about a third-party bank account.
- "Public Bank Berhad" and "Public Islamic Bank" are the SENDER — do NOT return them as the bank name unless there is absolutely no other bank present.
- You are looking for the name of the THIRD-PARTY bank whose account details (FI Num, Master Account, Sub Account) appear in the summary table described above. The bank name is usually printed near that table, in a letterhead block, or in the payment instruction section of the document.
- Common locations: letterhead/header of the third-party bank's section, "Beneficiary" label, "remit to" instructions, or a named address block belonging to that bank.
- Match the bank name to the closest entry in the known bank list below.
- Use the EXACT canonical form shown — strip suffixes such as "Berhad", "Malaysia Berhad", "(M) Berhad", or extra punctuation that do not appear in the known list (e.g. "HSBC Bank Malaysia -Berhad" -> "HSBC Bank", "HSBC Bank Malaysia Berhad" -> "HSBC Bank").
- If the document mentions "Bank Simpanan Nasional" or "BSN", return "BSN".
- If the document mentions an Islamic variant (e.g. "Maybank Islamic", "HSBC Amanah"), return the Islamic variant exactly as it appears in the list.
- Return null ONLY if no third-party bank can be identified at all.

Known bank names (return the EXACT canonical form from this list):
{_KNOWN_BANKS}

=== DOCUMENT ===
\"\"\"
{text}
\"\"\"

=== OUTPUT ===
Return ONLY this JSON object with no other text or explanation:
{{
    "name": "<full customer name or null>",
    "master_account_number": "<master account number or null>",
    "sub_account_number": "<sub account number or null>",
    "address": "<full address or null>",
    "fi_num": "<FI number or null>",
    "bank_name": "<canonical bank name from the known list, or null>"
}}
"""