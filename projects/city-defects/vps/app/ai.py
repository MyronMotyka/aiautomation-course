"""Розпізнавання фото дефекту через Claude Vision."""
import base64
import os
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

CATEGORIES = {
    "road": ("Дороги й тротуари", "Служба автомобільних доріг"),
    "lighting": ("Вуличне освітлення", "Міськсвітло"),
    "building": ("Аварійна будівля / споруда", "Інспекція з питань будівництва"),
    "trees": ("Дерева й озеленення", "Зеленбуд"),
    "waste": ("Сміття, стихійне звалище", "Служба благоустрою"),
    "water": ("Вода, каналізація, люки", "Водоканал"),
    "traffic": ("Знаки, світлофори, розмітка", "Відділ організації дорожнього руху"),
    "vandalism": ("Вандалізм, графіті", "Служба благоустрою"),
    "other": ("Інше", "Диспетчер (ручний розгляд)"),
}
EMERGENCY_DEPT = "Аварійно-диспетчерська служба"

Category = Literal["road", "lighting", "building", "trees", "waste", "water", "traffic", "vandalism", "other"]


class Analysis(BaseModel):
    is_valid_report: bool = Field(description="false, якщо на фото немає міської проблеми")
    reject_reason: str = Field(description="чому фото відхилено; порожньо, якщо прийнято")
    category: Category
    title: str = Field(description="коротка назва до 8 слів")
    description: str = Field(description="1-2 речення: що видно, розмір, розташування")
    severity: int = Field(description="1..5")
    is_emergency: bool
    hazards: list[str]
    recommended_action: str
    privacy: str = Field(description="чи видно обличчя або номери авто")
    confidence: float = Field(description="0..1")


PROMPT = """Ти — AI-диспетчер міської служби, що приймає скарги мешканців на дефекти міської інфраструктури.
Проаналізуй фото від мешканця. Відповідай українською.

Коментар мешканця: {comment}
Адреса: {address}

Категорії (поле category):
{categories}

Терміновість severity від 1 до 5:
1 — косметична проблема; 2 — незначна, можна планово; 3 — помірна, погіршує користування;
4 — серйозна, ризик травми чи пошкодження майна;
5 — пряма небезпека для життя (відкритий люк, обірвані дроти, загроза обвалу, дерево на дорозі).

Якщо на фото немає міської проблеми (селфі, мем, інтер'єр квартири, розмите фото),
постав is_valid_report=false і поясни чому в reject_reason, category=other."""

_client = anthropic.Anthropic()  # ключ береться з ANTHROPIC_API_KEY


def analyze(jpeg: bytes, comment: str, address: str) -> dict:
    cats = "\n".join(f"- {k}: {v[0]}" for k, v in CATEGORIES.items())
    response = _client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.standard_b64encode(jpeg).decode()}},
                {"type": "text", "text": PROMPT.format(comment=comment or "(немає)", address=address or "(не вказана)",
                                                        categories=cats)},
            ],
        }],
        output_format=Analysis,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError("AI відмовився аналізувати це фото")

    a = response.parsed_output
    severity = min(5, max(1, a.severity))
    emergency = a.is_emergency or severity == 5
    dept = CATEGORIES[a.category][1] if a.is_valid_report else CATEGORIES["other"][1]
    if emergency and a.is_valid_report:
        dept += " + " + EMERGENCY_DEPT
    return {
        "valid": a.is_valid_report,
        "reject_reason": a.reject_reason,
        "category": a.category,
        "category_name": CATEGORIES[a.category][0],
        "title": a.title[:120],
        "description": a.description[:600],
        "severity": severity,
        "emergency": emergency,
        "department": dept,
        "hazards": a.hazards[:5],
        "action": a.recommended_action[:400],
        "privacy": a.privacy[:200],
        "confidence": max(0.0, min(1.0, a.confidence)),
    }
