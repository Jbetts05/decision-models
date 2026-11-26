"""Extract bounded, photo-checkable questions from campaign documents with a generative model."""

import hashlib
import json
from datetime import datetime, timezone

from .catalog import CHECK_ID, validate_questions
from .foundry import FoundryError, usage_of

SYSTEM = """You turn retail campaign documents into a checklist for a photo audit.

A separate decision model will later answer each check by choosing exactly one of
"compliant", "not_compliant" or "cannot_assess" while looking only at the named
store photos (and, where stated, an approved reference image). It cannot read
documents, count beyond what is plainly visible, or know anything not shown.

Rules for checks:
- Write the checks an experienced store auditor would actually fail a display
  for: typically 8 to 16 per campaign. Combine details of the same item into one
  check (for example: "the Original Roast label is yellow and reads £3.50"; "each
  product is on the right shelf with at least its minimum facings"). Do not split
  one requirement into near-duplicates, and do not check fine details that cannot
  be judged at a glance (exact sticker height, which side, how a card is clipped).
- Cover the requirements a photo can verify: placement, order, minimum facings,
  gaps, brand blocking, other brands' products, price labels and their wording,
  campaign signage and point-of-sale material, damaged or fallen products,
  presentation, and whether equipment such as lights is working.
- Include checks for things that must be ABSENT, in particular material from an
  earlier campaign, products not in this campaign, and other brands' products.
- Never check the photograph itself (angle, framing, focus, lighting of the
  photo, whether everything is in shot). Unusable photos are handled separately
  by a "cannot assess" option. A cooler's own lights being off IS a display
  requirement, because shoppers see it.
- "photos" lists every photo type that normally shows the item clearly enough to
  judge, using only the supplied photo types. Close-ups show only part of the
  display: never list a close-up for whole-display requirements (which shelf the
  range is on, order across the range, gaps, splits across shelves, products
  anywhere in the fixture). Respect the documents' audit-evidence rules: if a
  document says prices are read from close-ups, do not list the full photo for
  price checks.
- Set "uses_reference" to true only when the campaign has an approved reference
  image and the check compares the store photo with it. Reference-image checks
  must say that positions may differ but the named items must match.
- "question" is a neutral instruction naming exactly what to look for.
  "compliant" and "not_compliant" describe concretely what each looks like.
  Do not describe blur or obstruction; the auditor adds that option.
- When the standards say something is required in the active campaign, write the
  check for this campaign's specifics (shelf, products, prices, signage).
- "rule" cites the source, such as "Standards 1.2" or "Brief: Pricing".
- ids are short lowercase snake_case.

Do NOT create checks for requirements a photo cannot verify. List them under
"not_checkable" with a reason:
- needs_hand_check: the documents say it is checked by hand, or it needs touching,
  reading dates, tills, thermometers or labels too small to see.
- timing_or_process: deadlines, frequencies, replenishment, reporting, payments,
  sign-off, anything that happened before or after the photo.
- subjective: vague wording such as "inviting" or "premium" that has no concrete
  visual test beyond the checks you already wrote.
- not_visible_in_photos: anything else outside the supplied photo types.
"""


def schema(photo_types):
    text = {"type": "string"}
    check = {
        "type": "object",
        "properties": {
            "id": text, "rule": text, "requirement": text,
            "photos": {"type": "array", "items": {"type": "string", "enum": sorted(photo_types)}},
            "uses_reference": {"type": "boolean"},
            "question": text, "compliant": text, "not_compliant": text,
        },
        "required": ["id", "rule", "requirement", "photos", "uses_reference", "question", "compliant", "not_compliant"],
        "additionalProperties": False,
    }
    skipped = {
        "type": "object",
        "properties": {
            "rule": text, "requirement": text,
            "reason": {"type": "string", "enum": ["needs_hand_check", "timing_or_process", "subjective", "not_visible_in_photos"]},
        },
        "required": ["rule", "requirement", "reason"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"checks": {"type": "array", "items": check},
                       "not_checkable": {"type": "array", "items": skipped}},
        "required": ["checks", "not_checkable"],
        "additionalProperties": False,
    }


def user_message(scenario, campaign):
    photo_lines = "\n".join(f"- {name}: {description}" for name, description in scenario["photo_types"].items())
    parts = [f"Scenario: {scenario['name']}", f"Campaign {campaign['id']}: {campaign['name']}",
             f"Photo types a visit may include:\n{photo_lines}"]
    parts.append("Approved reference image: yes, the campaign lookbook." if campaign.get("reference")
                 else "Approved reference image: none.")
    if campaign.get("standards_text"):
        parts.append("STANDARDS DOCUMENT (applies to this campaign):\n" + campaign["standards_text"])
    parts.append("CAMPAIGN BRIEF:\n" + campaign["brief_text"])
    return "\n\n".join(parts)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract(client, scenario, campaign, deployment, reasoning_effort="high"):
    body = {
        "model": deployment,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user_message(scenario, campaign)}],
        "reasoning_effort": reasoning_effort,
        "max_completion_tokens": 32000,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "audit_checks", "strict": True, "schema": schema(scenario["photo_types"])}},
    }
    payload, latency_ms = client.post("/openai/v1/chat/completions", body, timeout=600)
    try:
        choice = payload["choices"][0]
        if choice["finish_reason"] != "stop":
            raise FoundryError(f"Extraction did not finish: {choice['finish_reason']}.")
        result = json.loads(choice["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise FoundryError("Extraction returned an unexpected response.") from exc
    for check in result["checks"]:
        if not CHECK_ID.match(check["id"]):
            raise FoundryError(f"Extraction returned an invalid id: {check['id']!r}.")
        if check["uses_reference"] and not campaign.get("reference"):
            raise FoundryError(f"Check {check['id']} uses a reference image the campaign does not have.")
    validate_questions(result, scenario["photo_types"], campaign["id"])
    sources = {"brief": digest(campaign["brief_text"])}
    if campaign.get("standards_text"):
        sources["standards"] = digest(campaign["standards_text"])
    return {
        "campaign": campaign["id"],
        "extraction": {
            "model": payload.get("model"), "deployment_role": "extraction",
            "reasoning_effort": reasoning_effort,
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_sha256_prefix": sources, "usage": usage_of(payload), "latency_ms": latency_ms,
        },
        "review": {"status": "pending", "notes": []},
        "checks": result["checks"],
        "not_checkable": result["not_checkable"],
    }
