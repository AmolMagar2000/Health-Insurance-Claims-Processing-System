"""
utils/azure_client.py
=====================
Azure OpenAI GPT-4.1-mini client for document extraction.

Completely separate from gemini_client.py — this file has NO dependency
on the Gemini SDK. Drop it in, set the env vars, and the extractor
will automatically use it for image (vision) extraction.

Configuration (set in backend/.env):
  AZURE_OPENAI_ENDPOINT   = https://demovisionapi.openai.azure.com/
  AZURE_OPENAI_KEY        = your-subscription-key
  AZURE_OPENAI_DEPLOYMENT = gpt-4.1-mini
  AZURE_OPENAI_API_VERSION= 2024-12-01-preview

The extract_document() method has the SAME signature as GeminiClient
so the extractor node can swap between them with zero logic changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

# ── Try to import Azure OpenAI SDK ────────────────────────────────────────
try:
    from openai import AzureOpenAI   # type: ignore
    _AZURE_SDK_AVAILABLE = True
except ImportError:
    _AZURE_SDK_AVAILABLE = False
    logger.warning("openai package not installed — Azure client unavailable. Run: pip install openai")


# ── Prompt shared with Gemini client ─────────────────────────────────────
VISION_PROMPT = """You are a medical document OCR expert for an Indian health insurance company.

Look at this medical document image carefully. Extract ALL visible fields.
Return ONLY a valid JSON object — no markdown fences, no explanation, no extra text.

Required fields (use null if not found):
{
  "patient_name":        string or null,
  "doctor_name":         string or null,
  "doctor_registration": string or null,
  "hospital_name":       string or null,
  "diagnosis":           string or null,
  "treatment":           string or null,
  "medicines":           list of strings,
  "line_items":          list of {"description": str, "amount": number},
  "total_amount":        number or null,
  "date":                string or null,
  "tests_ordered":       list of strings,
  "invoice_number":      string or null,
  "gstin":               string or null
}

Document type: %s

Tips for accuracy:
- For pharmacy bills: extract every medicine/drug line item with its price.
- Grand Total / Net Amount / Net Payable → total_amount field.
- Look for "Reg. No." or "Registration No." for doctor_registration.
- Be precise with rupee amounts — read every digit carefully.
- If a field is genuinely not visible, return null (do not guess).
"""

TEXT_PROMPT = """You are a medical document parser for an Indian health insurance company.

Extract ALL of the following fields from the document content below.
If a field is missing, use null — do NOT guess.

Fields to extract:
- patient_name, doctor_name, doctor_registration, diagnosis, treatment
- medicines (list), line_items (list of {description, amount}), total_amount
- hospital_name, date, tests_ordered (list)

Document type: %s
Document content:
%s

Return ONLY a valid JSON object. No markdown. No extra text.
"""


class AzureOpenAIClient:
    """
    Azure OpenAI wrapper with the same extract_document() interface as GeminiClient.

    Supports:
      - Vision extraction (base64 image → GPT-4.1-mini with vision)
      - Text extraction (content dict → chat completion)
      - OCR fallback (when Azure is unavailable)
    """

    def __init__(self):
        self.endpoint   = os.getenv("AZURE_OPENAI_ENDPOINT",    "https://demovisionapi.openai.azure.com/")
        self.api_key    = os.getenv("AZURE_OPENAI_KEY",         "")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT",  "gpt-4.1-mini")
        self.api_version= os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        self._client    = None

        if _AZURE_SDK_AVAILABLE and self.api_key:
            self._client = AzureOpenAI(
                api_version    = self.api_version,
                azure_endpoint = self.endpoint,
                api_key        = self.api_key,
            )
            logger.info(
                "Azure OpenAI client ready: endpoint=%s deployment=%s",
                self.endpoint, self.deployment
            )
        else:
            if not _AZURE_SDK_AVAILABLE:
                logger.warning("openai SDK missing — run: pip install openai")
            elif not self.api_key:
                logger.warning("AZURE_OPENAI_KEY not set — Azure client disabled")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    # ── Public entry point (same signature as GeminiClient) ──────────────

    async def extract_document(
        self,
        document: Dict[str, Any],
        simulate_failure: bool = False,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Extract structured data from a document.
        Returns (extracted_dict, method_used).
        """
        if simulate_failure:
            return await self._ocr_fallback(document)

        # Fast path: pre-extracted test fixture
        if document.get("content"):
            return self._passthrough_content(document), "content_passthrough"

        # Real image → GPT-4.1-mini vision
        if document.get("base64_data"):
            if self._client:
                for attempt in range(3):
                    try:
                        result = await self._call_vision(document)
                        return result, "azure_vision"
                    except Exception as exc:
                        logger.warning(
                            "Azure vision attempt %d/%d failed: %s",
                            attempt + 1, 3, exc
                        )
                        if attempt < 2:
                            await asyncio.sleep(1.5 ** attempt)
            logger.info("Azure vision unavailable — falling back to OCR")
            return await self._ocr_fallback(document)

        # Text-based extraction (no image)
        if self._client:
            for attempt in range(3):
                try:
                    result = await self._call_text(document)
                    return result, "azure_text"
                except Exception as exc:
                    logger.warning("Azure text attempt %d failed: %s", attempt + 1, exc)
                    if attempt < 2:
                        await asyncio.sleep(1.5 ** attempt)

        return await self._ocr_fallback(document)

    # ── Private helpers ───────────────────────────────────────────────────

    async def _call_vision(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send image to GPT-4.1-mini vision via Azure OpenAI.
        Uses the standard OpenAI multimodal message format:
          content = [{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":...}}]
        """
        doc_type  = document.get("actual_type", "UNKNOWN")
        mime_type = document.get("mime_type", "image/jpeg")
        b64_data  = document["base64_data"]
        data_url  = f"data:{mime_type};base64,{b64_data}"

        prompt = VISION_PROMPT % doc_type

        logger.info(
            "Sending image to Azure GPT-4.1-mini vision | doc_type=%s mime=%s size=~%dKB",
            doc_type, mime_type, len(b64_data) * 3 // 4 // 1024
        )

        loop     = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.chat.completions.create(
                model    = self.deployment,
                messages = [{
                    "role": "user",
                    "content": [
                        {"type": "text",      "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
                max_completion_tokens = 2000,
                temperature           = 0.0,   # deterministic extraction
            )
        )

        raw_text = response.choices[0].message.content
        logger.info("Azure vision raw response (first 200 chars): %s", raw_text[:200])

        extracted = self._parse_json_response(raw_text)
        extracted["_extraction_method"] = "azure_vision"
        extracted["_confidence"]        = "HIGH"
        return extracted

    async def _call_text(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Text-based extraction for non-image documents."""
        doc_type = document.get("actual_type", "UNKNOWN")
        prompt   = TEXT_PROMPT % (doc_type, json.dumps(document, indent=2))

        loop     = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.chat.completions.create(
                model    = self.deployment,
                messages = [
                    {"role": "system", "content": "You are a precise medical document parser. Return only valid JSON."},
                    {"role": "user",   "content": prompt},
                ],
                max_completion_tokens = 1500,
                temperature           = 0.0,
            )
        )

        raw_text = response.choices[0].message.content
        return self._parse_json_response(raw_text)

    async def _ocr_fallback(
        self, document: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], str]:
        """Skeleton OCR result when Azure is completely unavailable."""
        logger.info("OCR fallback activated for document %s", document.get("file_id"))
        return {
            "patient_name": None, "doctor_name": None, "doctor_registration": None,
            "diagnosis": None, "treatment": None, "medicines": [], "line_items": [],
            "total_amount": None, "hospital_name": None, "date": None,
            "tests_ordered": [], "_extraction_method": "ocr_fallback", "_confidence": "LOW",
        }, "ocr_fallback"

    def _passthrough_content(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise a pre-extracted test fixture into the standard schema."""
        raw = document.get("content", {})
        return {
            "patient_name":        raw.get("patient_name"),
            "doctor_name":         raw.get("doctor_name"),
            "doctor_registration": raw.get("doctor_registration"),
            "diagnosis":           raw.get("diagnosis"),
            "treatment":           raw.get("treatment"),
            "medicines":           raw.get("medicines", []),
            "line_items":          raw.get("line_items", []),
            "total_amount":        raw.get("total") or raw.get("total_amount"),
            "hospital_name":       raw.get("hospital_name"),
            "date":                raw.get("date"),
            "tests_ordered":       raw.get("tests_ordered", []),
            "_extraction_method":  "content_passthrough",
            "_confidence":         "HIGH",
        }

    @staticmethod
    def _parse_json_response(text: str) -> Dict[str, Any]:
        """Strip markdown fences and parse JSON from a model response."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$",          "", text, flags=re.MULTILINE)
        return json.loads(text)
