'''
import json
import httpx
from fastapi import HTTPException

from app.core.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }

        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

        return headers

    def _normalize_llm_output(self, response_json: dict) -> dict:
        """
        Accept a few possible response shapes from the LLM microservice.
        Adjust here later if your senior's service has a fixed format.
        """

        # Case 1: microservice already returns extracted JSON directly
        if "name" in response_json or "account_number" in response_json:
            return {
                "name": response_json.get("name"),
                "account_number": response_json.get("account_number"),
            }

        # Case 2: microservice returns string content that contains JSON
        if "content" in response_json and isinstance(response_json["content"], str):
            try:
                parsed = json.loads(response_json["content"])
                return {
                    "name": parsed.get("name"),
                    "account_number": parsed.get("account_number"),
                }
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="LLM response content is not valid JSON",
                ) from exc

        # Case 3: OpenAI-style shape
        if "choices" in response_json and isinstance(response_json["choices"], list):
            try:
                content = response_json["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return {
                    "name": parsed.get("name"),
                    "account_number": parsed.get("account_number"),
                }
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Unsupported LLM response format in choices",
                ) from exc

        raise HTTPException(
            status_code=502,
            detail="Unsupported LLM response format",
        )

    async def extract_fields(self, prompt: str) -> dict[str, str | None]:
        payload = {
            "prompt": prompt,
            "model": self.settings.llm_model_name,
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(
                    self.settings.llm_url,
                    headers=self._build_headers(),
                    json=payload,
                )

            response.raise_for_status()
            response_json = response.json()
            return self._normalize_llm_output(response_json)

        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504,
                detail="LLM microservice timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"LLM microservice returned error status: {exc.response.status_code}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail="Unable to connect to LLM microservice",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="LLM microservice returned invalid JSON",
            ) from exc
        '''

import re
from app.core.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def extract_fields(self, prompt: str) -> dict[str, str | None]:
        """
        MOCK LLM FUNCTION

        Instead of calling real microservice,
        we simulate extraction using regex.

        Later: replace this function with real API call.
        """

        # Extract text part from prompt (everything inside triple quotes)
        text_match = re.search(r'"""(.*?)"""', prompt, re.DOTALL)

        if not text_match:
            return {
                "name": None,
                "account_number": None
            }

        text = text_match.group(1)

        # ---- Mock extraction logic ----

        name = None
        account_number = None

        # Name patterns
        name_patterns = [
            r"Customer Name[:\-\s]+(.+)",
            r"Account Name[:\-\s]+(.+)",
            r"Name[:\-\s]+(.+)"
        ]

        # Account patterns
        account_patterns = [
            r"Account Number[:\-\s]+([\w\- ]+)",
            r"Acc No[:\-\s]+([\w\- ]+)",
            r"Account No[:\-\s]+([\w\- ]+)"
        ]

        # Find name
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                break

        # Find account number
        for pattern in account_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                account_number = match.group(1).strip()
                break

        return {
            "name": name,
            "account_number": account_number
        }