"""
utils/gemini_client.py
======================
Wraps Google Gemini for document data extraction.

Two extraction paths:
  A. Text-prompt path  — for test fixtures (no image data needed)
  B. Vision path       — for real uploaded images (base64_data present)
         uses gemini-1.5-flash multimodal capability

Fallback chain (as specified in the assignment):
  1. Gemini API call
  2. Retry up to 2 times on failure
  3. Simulated OCR + LLM normalisation
  4. If all fail → signal MANUAL_REVIEW
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai  # type: ignore
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed — Gemini calls will use mock fallback")


class GeminiClient:
    """
    Thin wrapper around the Gemini 1.5 Flash API.
    Supports both text-prompt extraction (test mode) and
    multimodal vision extraction (real image uploads).
    """

    # ── Text extraction prompt (for test fixtures) ────────────────────────
    EXTRACTION_PROMPT = """
You are a medical document parser for an Indian health insurance company.

Extract ALL of the following fields from the document content below.
If a field is missing, use null — do NOT guess.

Fields to extract:
- patient_name        (string)
- doctor_name         (string)
- doctor_registration (string, e.g. KA/45678/2015)
- diagnosis           (string)
- treatment           (string or null)
- medicines           (list of strings)
- line_items          (list of {{"description": str, "amount": number}})
- total_amount        (number)
- hospital_name       (string or null)
- date                (string, DD-Mon-YYYY format)
- tests_ordered       (list of strings)

Document type: {doc_type}
Document content:
{content}

IMPORTANT: Return ONLY a valid JSON object. No markdown. No extra text.
"""

    # ── Vision prompt (for real uploaded images) ──────────────────────────
    VISION_PROMPT = """You are a medical document OCR expert for an Indian health insurance company.

Look at this medical document image carefully. Extract ALL visible fields.
Return ONLY a valid JSON object — no markdown fences, no extra text.

Required fields (use null if not found):
{{
  "patient_name":        string or null,
  "doctor_name":         string or null,
  "doctor_registration": string or null,
  "hospital_name":       string or null,
  "diagnosis":           string or null,
  "treatment":           string or null,
  "medicines":           list of strings,
  "line_items":          list of {{"description": str, "amount": number}},
  "total_amount":        number or null,
  "date":                string or null,
  "tests_ordered":       list of strings,
  "invoice_number":      string or null,
  "gstin":               string or null
}}

Document type: {doc_type}

Notes:
- For pharmacy bills: extract every medicine line item with its amount.
- For hospital bills: extract every service/procedure line item.
- Grand Total / Net Amount → total_amount.
- Look for "Reg. No." or "Registration No." for doctor_registration.
- Be precise with amounts — read the numbers carefully.
"""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self._model  = None

        if _GEMINI_AVAILABLE and self.api_key:
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel("Gemini 2.0 Flash")
            logger.info("Gemini 2.0 Flash model loaded successfully")

    # ── Public entry point ────────────────────────────────────────────────

    async def extract_document(
        self,
        document: Dict[str, Any],
        simulate_failure: bool = False,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Extract structured data from one document.

        Returns (extracted_dict, method_used) where method_used is one of:
          "gemini_vision" | "gemini" | "ocr_fallback" | "content_passthrough"
        """
        # ── Force failure for TC011 (simulate_failure must check FIRST) ─────
        if simulate_failure:
            logger.info("Simulating Gemini failure (TC011 test)")
            return await self._ocr_fallback(document)

        # ── Fast path: test fixture with pre-extracted content ───────────────
        if document.get("content"):
            return self._passthrough_content(document), "content_passthrough"

        # ── Real image upload → Gemini Vision (multimodal) ───────────────────
        if document.get("base64_data"):
            if self._model:
                for attempt in range(3):
                    try:
                        result = await self._call_gemini_vision(document)
                        return result, "gemini_vision"
                    except Exception as exc:
                        logger.warning("Gemini vision attempt %d failed: %s", attempt + 1, exc)
                        if attempt < 2:
                            await asyncio.sleep(1.5 ** attempt)
            # No model available or all retries failed
            logger.info("Gemini vision unavailable — using OCR fallback")
            return await self._ocr_fallback(document)

        # ── Text-prompt path (no image, no content) ───────────────────────────
        if self._model:
            for attempt in range(3):
                try:
                    result = await self._call_gemini(document)
                    return result, "gemini"
                except Exception as exc:
                    logger.warning("Gemini attempt %d failed: %s", attempt + 1, exc)
                    if attempt < 2:
                        await asyncio.sleep(1.5 ** attempt)

        return await self._ocr_fallback(document)

    # ── Private helpers ───────────────────────────────────────────────────

    async def _call_gemini_vision(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send the document image to Gemini 1.5 Flash using its vision capability.
        Gemini reads the raw image bytes directly — no need to describe image quality.
        """
        doc_type   = document.get("actual_type", "UNKNOWN")
        mime_type  = document.get("mime_type", "image/jpeg")
        b64_data   = document["base64_data"]
        image_bytes = base64.b64decode(b64_data)

        prompt = self.VISION_PROMPT.format(doc_type=doc_type)

        # Build the multimodal content: [image_part, text_part]
        image_part = {"mime_type": mime_type, "data": image_bytes}

        loop     = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._model.generate_content([
                {"parts": [{"inline_data": image_part}, {"text": prompt}]}
            ])
        )
        extracted = self._parse_json_response(response.text)
        extracted["_extraction_method"] = "gemini_vision"
        extracted["_confidence"]        = "HIGH"
        return extracted

    async def _call_gemini(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Text-prompt Gemini call for non-image documents."""
        prompt = self.EXTRACTION_PROMPT.format(
            doc_type=document.get("actual_type", "UNKNOWN"),
            content=json.dumps(document, indent=2),
        )
        loop     = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._model.generate_content(prompt)
        )
        return self._parse_json_response(response.text)

    async def _ocr_fallback(
        self, document: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], str]:
        """
        OCR fallback — called when Gemini is unavailable.
        In production this calls Tesseract/PaddleOCR on the image.
        Returns a skeleton extraction so the pipeline can still decide.
        """
        logger.info("OCR fallback for document %s", document.get("file_id"))
        result: Dict[str, Any] = {
            "patient_name":        None,
            "doctor_name":         None,
            "doctor_registration": None,
            "diagnosis":           None,
            "treatment":           None,
            "medicines":           [],
            "line_items":          [],
            "total_amount":        None,
            "hospital_name":       None,
            "date":                None,
            "tests_ordered":       [],
            "_extraction_method":  "ocr_fallback",
            "_confidence":         "LOW",
        }
        return result, "ocr_fallback"

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
        """Strip markdown fences and parse JSON from a Gemini response."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$",          "", text, flags=re.MULTILINE)
        return json.loads(text)
