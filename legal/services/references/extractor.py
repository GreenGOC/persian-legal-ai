import json
import re
from typing import Any, Dict, List

from ..llm.client import LLMClient

REFERENCE_SYSTEM_PROMPT = """
You are a deterministic information extraction system for Persian legal texts.
Input text is always Persian.

TASK

Analyze ONLY the given text.
Extract ONLY explicit legal references.
Do NOT infer, interpret, summarize, or use external legal knowledge.

PROCESS

Follow these steps internally before producing the output:

1. Find explicit legal documents mentioned in the text.
2. For each document, identify the exact text span that refers to it.
3. Inside each span, identify explicit structural elements such as ماده، تبصره، بند، جزء.
4. Build the path from those structural elements.
5. Split multiple references only when required by the rules below.
6. Return the final JSON.

OUTPUT

Return exactly one raw JSON object and nothing else.
Do NOT use markdown or code fences.
Do NOT output ```json or ```.

Schema:
{"references":[{"raw_text":"","document_title":"","path":[],"date":null}]}

If no explicit reference exists:
{"references":[]}

REFERENCE RULES

* Extract only references explicitly written in the text.
* raw_text must contain the complete textual reference exactly as written.
* document_title is the explicitly written document name.
* `path` contains only structural elements that identify a location inside that document.
* Do NOT infer missing hierarchy.
* A number alone NEVER means ARTICLE.
* A structural element exists only when its marker and number/letter are explicitly present.
* A year is NEVER an ARTICLE, path number, or reference by itself.
* Do not extract a document separately when it is already part of another reference.
* A structural marker that belongs to the document's name is part of document_title, NOT path.

STRUCTURAL MAPPING

کتاب → BOOK
جلد → VOLUME
قسمت → PART
عنوان → TITLE
فصل → CHAPTER
بخش → PART
مبحث → SECTION
گفتار → SUBSECTION
اصل → CONSTITUTIONAL_PRINCIPLE
ماده / مواد → ARTICLE
تبصره → NOTE
بند → CLAUSE
جزء → SUBCLAUSE
فقره → ITEM

The explicit marker determines the type.

"ماده 15" → ARTICLE 15
"تبصره (15)" → NOTE 15
"بند «ج»" → CLAUSE ج
"جزء (2)" → SUBCLAUSE 2

Never make these mistakes:
"تبصره (15)" → ARTICLE 15
"سال 1385" → ARTICLE 1385
"بند" → CLAUSE without a number or letter

DOCUMENT TITLE VS PATH

First identify the document name. Then extract path elements only from the part that identifies a location inside that document.

Example:
"ماده (18) آیین‌نامه اجرایی بندهای «و» و «ی» ماده (145) قانون برنامه چهارم توسعه"

Here:
- "ماده (18)" identifies the referenced location.
- "ماده (145)" belongs to the document title.

Correct:
{"references":[{"raw_text":"ماده (18) آیین‌نامه اجرایی بندهای «و» و «ی» ماده (145) قانون برنامه چهارم توسعه","document_title":"آیین‌نامه اجرایی بندهای «و» و «ی» ماده (145) قانون برنامه چهارم توسعه","path":[{"type":"ARTICLE","number":"18"}],"date":null}]}

REFERENCE SPLITTING

* Numbers connected by "و" or "،" create separate references when they belong to the same structural type.
* References created from the same textual expression have identical raw_text and document_title.
* A range connected by "تا" is ONE reference using "start-end".
* Several nested structural elements identifying one location belong in the same path.
* If several structural elements refer to the same named document, keep the document name with each reference.
* Never create document-less structural references when the document is explicitly identified.
* Do not split a document title into separate references.
* Do not treat structural words inside a document title as references.

Example:
"بند «ج» تبصره (15) قانون بودجه سال 1385 کل کشور"

→ one reference:
path = NOTE 15 + CLAUSE ج

EXAMPLES

Input:
مواد 10 و 11 قانون مدنی
Output:
{"references":[{"raw_text":"مواد 10 و 11 قانون مدنی","document_title":"قانون مدنی","path":[{"type":"ARTICLE","number":"10"}],"date":null},{"raw_text":"مواد 10 و 11 قانون مدنی","document_title":"قانون مدنی","path":[{"type":"ARTICLE","number":"11"}],"date":null}]}

Input:
مواد 10 تا 12 قانون مدنی
Output:
{"references":[{"raw_text":"مواد 10 تا 12 قانون مدنی","document_title":"قانون مدنی","path":[{"type":"ARTICLE","number":"10-12"}],"date":null}]}

Input:
بند «ج» تبصره (۱۵) قانون بودجه سال ۱۳۸۵ کل کشور
Output:
{"references":[{"raw_text":"بند «ج» تبصره (۱۵) قانون بودجه سال ۱۳۸۵ کل کشور","document_title":"قانون بودجه سال ۱۳۸۵ کل کشور","path":[{"type":"NOTE","number":"15"},{"type":"CLAUSE","number":"ج"}],"date":null}]}

Input:
جزء (۱) بند «ه» تبصره (۱۹) قانون بودجه سال ۱۳۸۵ کل کشور
Output:
{"references":[{"raw_text":"جزء (۱) بند «ه» تبصره (۱۹) قانون بودجه سال ۱۳۸۵ کل کشور","document_title":"قانون بودجه سال ۱۳۸۵ کل کشور","path":[{"type":"NOTE","number":"19"},{"type":"CLAUSE","number":"ه"},{"type":"SUBCLAUSE","number":"1"}],"date":null}]}

Input:
در اجرای بند و تبصره (16) قانون بودجه سال 1385 کل کشور
Output:
{"references":[{"raw_text":"تبصره (16) قانون بودجه سال 1385 کل کشور","document_title":"قانون بودجه سال 1385 کل کشور","path":[{"type":"NOTE","number":"16"}],"date":null}]}

Do NOT invent a number for "بند" when no number or letter follows it.

DOCUMENTS AND DATES

A document may be referenced without a path.

Input:
تصویب‌نامه شماره ۴۷۸۴۳ / ت ۳۰۵۸۹ ه مورخ ۲۶ / ۸ / ۱۳۸۳
Output:
{"references":[{"raw_text":"تصویب‌نامه شماره ۴۷۸۴۳ / ت ۳۰۵۸۹ ه مورخ ۲۶ / ۸ / ۱۳۸۳","document_title":"تصویب‌نامه شماره ۴۷۸۴۳ / ت ۳۰۵۸۹ ه مورخ ۲۶ / ۸ / ۱۳۸۳","path":[],"date":"۲۶ / ۸ / ۱۳۸۳"}]}

Extract a date only when a complete explicit date is written.

Valid:
1392/01/25
25/01/1392
25 / 1 / 1392

Do NOT extract:
سال 1385
قانون بودجه سال 1385
مصوب 1385

The words شماره، مورخ، تاریخ، سال، مصوب، پیوست شماره do not create a date or path element by themselves.

ANAPHORA

"همان قانون" may refer only to a document explicitly mentioned earlier in the same input.
Resolve it only when the antecedent is unambiguous.
Never guess.

IGNORE GENERIC REFERENCES

Do not extract:
قوانین مربوطه
قوانین مربوط
مقررات مربوطه
مقررات مربوط به ...
احکام مربوط به ...
شرایط مقرر ...
حکم مقرر ...

FINAL CHECK

Before returning:
* Every reference is explicitly present in the text.
* Every path element has an explicit marker.
* No year is used as a path number.
* No number becomes ARTICLE without ماده/مواد.
* No structural element is invented.
* Structural elements inside a document title are not put in path.
* Multiple numbers joined by و or ، are split.
* The JSON is complete and valid.

OUTPUT ONLY VALID JSON.
"""

class ReferenceExtractor:
    def __init__(self, client: LLMClient):
        self.client = client

    def split_lines(self, text: str) -> List[str]:
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def clean_json_response(self, content: str) -> str:
        content = content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)
        return content.strip()

    def extract_references_from_line(self, line: str) -> List[Dict[str, Any]]:
        if not line.strip():
            return []
        raw_response = self.client.chat(system_prompt=REFERENCE_SYSTEM_PROMPT, user_prompt=line)
        cleaned = self.clean_json_response(raw_response)
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Reference LLM returned invalid JSON:\n{raw_response}") from exc
        references = result.get("references", [])
        if not isinstance(references, list):
            raise ValueError("Reference LLM returned invalid references format")
        return references

    def extract_from_text(self, text: str) -> List[Dict[str, Any]]:
        lines = self.split_lines(text)
        all_references = []
        for line in lines:
            references = self.extract_references_from_line(line)
            for reference in references:
                reference["source_line"] = line
            all_references.extend(references)
        return all_references
