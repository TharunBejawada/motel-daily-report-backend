# app/parsers/openai_parser.py
import os
import re
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class OpenAIReportParser:
    def parse(self, text: str, metadata=None) -> dict:
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0.2,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert OCR text parser for motel daily reports. "
                            "Return ONLY a valid JSON object with the following keys:\n"
                            "- property_name\n- report_date\n- department\n- auditor\n"
                            "- revenue\n- adr\n- occupancy\n- vacant_clean\n- vacant_dirty\n- out_of_order_rooms_storage\n"
                            "- vacant_dirty_rooms (list of {room_number, reason, days, action})\n"
                            "- out_of_order_rooms (list of {room_number, reason, days, action})\n"
                            "- comp_rooms (list of {room_number, notes})\n"
                            "- incidents (list of {description})\n\n"
                            "Do NOT include any explanations, prose, or markdown — only pure JSON."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Parse and return structured JSON from the following motel daily report text:\n\n{text}"
                    }
                ]
            )

            raw = response.choices[0].message.content.strip()
            print("📦 GPT Raw Output Preview:", raw[:400])

            # --- Clean & extract JSON ---
            json_str = self._extract_json_from_text(raw)
            if not json_str:
                print("⚠️ No valid JSON detected in GPT response.")
                return {}

            parsed = json.loads(json_str)
            return parsed

        except json.JSONDecodeError as e:
            print(f"⚠️ JSON decoding failed: {e}")
            return {}
        except Exception as e:
            print(f"[OpenAI Parser Error] {e}")
            return {}

    def _extract_json_from_text(self, text: str) -> str:
        """
        Extract JSON object from mixed GPT output. Handles explanations, markdown, etc.
        """
        match = re.search(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}", text, re.DOTALL)
        return match.group(0) if match else ""
