from openai import OpenAI
import json
import os
import random

# ⚠️ مفتاح OpenAI
<<<<<<< Updated upstream
OPENAI_API_KEY = ""
=======
OPENAI_API_KEY = "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"
>>>>>>> Stashed changes

client = OpenAI(api_key=OPENAI_API_KEY)


class AIService:
    # نستخدم الموديل الذكي والسريع
    model_name = "gpt-4o-mini"

    @staticmethod
    def generate_bio(name, teach_skills, learn_skills, headline=""):
        """
        توليد بايو باستخدام طبيعة ChatGPT الخام.
        يعتمد على العشوائية الطبيعية للموديل بدون فلاتر معقدة.
        """

        # رسالة النظام: نعطيه هوية عامة فقط
        system_msg = "You are a helpful creative writing assistant."

        # رسالة المستخدم: بسيطة ومباشرة مثل الشات
        user_msg = f"""
        I need a professional LinkedIn bio for a user.

        Here is the info:
        - Name: {name}
        - Headline: {headline if headline else "Member"}
        - Teaches: {teach_skills if teach_skills else "General Topics"}
        - Learns: {learn_skills if learn_skills else "New Things"}

        Task:
        Write a creative, human-sounding bio (max 2 sentences).
        Try to find a nice link between what they teach and what they learn.

        Note: Make it sound fresh and different each time I ask.
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                # Temperature 1.0 تعني العشوائية القياسية لـ ChatGPT (مبدع ومتغير)
                temperature=1.0,
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI Bio Error: {e}")
            return f"{headline} | Passionate about {teach_skills} & {learn_skills}."

    @staticmethod
    def get_smart_matches(learner_interests, teachers_list):
        # كود المطابقة يبقى كما هو لأنه يحتاج دقة وليس إبداعاً
        if not learner_interests: return []
        teachers_json = json.dumps(teachers_list)

        system_msg = "You are a matchmaking engine. Return ONLY valid JSON."
        user_msg = f"Learner Wants: {learner_interests}\nMentors: {teachers_json}\nFind top 3 matches."

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            if "matches" in data: return data["matches"]
            return []
        except Exception as e:
            print(f"Match Error: {e}")
            return []