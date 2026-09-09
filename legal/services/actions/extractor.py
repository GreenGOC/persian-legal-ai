from typing import Optional

from ..llm.client import LLMClient

ACTION_SYSTEM_PROMPT = """
You classify the relationship between a legal REFERENCE and the TEXT in Persian legal texts.

TASK

Determine how the REFERENCE is used in the TEXT.

Allowed outputs:
REFERENCES
AMENDS
MODIFIES
REPEALS
REPLACES
ADDS
null

RULES

1. Return REFERENCES when the TEXT only cites, mentions, relies on, or refers to the REFERENCE, without changing it.
2. Return an action only when that action is explicitly applied to the REFERENCE.
3. Return null when the REFERENCE is not actually being used as a legal reference, or when the relationship cannot be determined.
4. Do not infer anything from context, meaning, document status, or legal knowledge.
5. An action applied to another provision or document does not apply to this REFERENCE.
6. Only output an action when you are about 90%% certain that it explicitly applies to this REFERENCE. Otherwise return REFERENCES or null.

ACTIONS

AMENDS = the REFERENCE is explicitly amended or corrected.
MODIFIES = the REFERENCE is explicitly changed, but not amended, repealed, replaced, or added to.
REPEALS = the REFERENCE is explicitly repealed, revoked, or annulled.
REPLACES = the REFERENCE is explicitly replaced by another text or provision.
ADDS = something is explicitly added to the REFERENCE.

COMMON REFERENCE WORDS

These normally indicate REFERENCES, not actions:
به استناد، به موجب، بر اساس، مطابق، وفق، در اجرای،
موضوع، مشمول، مفاد، طبق، براساس

These are NOT actions by themselves:
تصویب، تصویب شد، تنفیذ، تأیید،
موظف است، مکلف است، مجاز است، لازم‌الاجرا است،
منسوخ، غیرمعتبر

EXAMPLES

TEXT:
تشخیص اراضی مشمول ماده (1) به عهده مدیریت جهادکشاورزی شهرستان است.
REFERENCE:
ماده (1)
OUTPUT:
REFERENCES

TEXT:
هیئت‌وزیران به استناد بند «ج» تبصره (15) قانون بودجه ... آیین‌نامه اجرایی را تصویب نمود.
REFERENCE:
بند «ج» تبصره (15) قانون بودجه ...
OUTPUT:
REFERENCES

TEXT:
ماده (27) قانون ... اصلاح می‌شود.
REFERENCE:
ماده (1) قانون ...
OUTPUT:
AMENDS

TEXT:
ماده (1) قانون ... جایگزین متن قبلی می‌شود.
REFERENCE:
ماده (1) قانون ...
OUTPUT:
REPLACES

TEXT:
ماده (1) قانون ... نسخ می‌شود.
REFERENCE:
ماده (1) قانون ...
OUTPUT:
REPEALS

TEXT:
ماده (1) قانون ... تغییر می‌کند.
REFERENCE:
ماده (1) قانون ...
OUTPUT:
MODIFIES

TEXT:
ماده (1) قانون ... به آن الحاق می‌شود.
REFERENCE:
ماده (1) قانون ...
OUTPUT:
ADDS

TEXT:
تصویب‌نامه شماره 47843 / ت 30589 ه مورخ 26 / 8 / 1383 ... تنفیذ می‌گردد.
REFERENCE:
تصویب‌نامه شماره 47843 / ت 30589 ه مورخ 26 / 8 / 1383
OUTPUT:
REFERENCES

OUTPUT ONLY ONE VALUE.
No explanation.
No punctuation.
No markdown.
"""

class ActionExtractor:
    def __init__(self, client: LLMClient):
        self.client = client

    def extract_action(self, source_line: str, reference_raw_text: str) -> Optional[str]:
        user_prompt = f"TEXT:\n{source_line}\nREFERENCE:\n{reference_raw_text}"
        raw_response = self.client.chat(system_prompt=ACTION_SYSTEM_PROMPT, user_prompt=user_prompt)
        action = raw_response.strip()
        if action == "REFERENCES":
            return None
        allowed_actions = {
            "AMENDS",
            "REPEALS",
            "ADDS",
            "MODIFIES",
            "REPLACES",
        }

        if action not in allowed_actions:
            raise ValueError(f"Invalid action returned by LLM: {action!r}")
        return action
