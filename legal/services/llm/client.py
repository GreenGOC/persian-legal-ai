from openai import OpenAI

class LLMClient:
    def __init__(self, base_url, api_key, model, timeout=60):
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    def chat(self, system_prompt, user_prompt, temperature=0):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=temperature)
        return response.choices[0].message.content
