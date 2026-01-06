from openai import OpenAI

# تأكد من وضع المفتاح الخاص بك هنا
OPENAI_API_KEY = "sk-proj-..."
client = OpenAI(api_key=OPENAI_API_KEY)


class AIService:
    @staticmethod
    def generate_bio(name, teach_skills, learn_skills, headline=""):
        """
        نسخة 'المخ الذكي' - تقوم بتحليل الروابط بين المهارات وصياغة بايو فريد في كل مرة.
        """

        # رسالة النظام: نحدد شخصية الـ AI كخبير تسويق شخصي
        system_msg = (
            "You are a world-class personal branding expert. You write punchy, professional, "
            "and slightly witty bios for a high-end skill-swapping platform. "
            "Your goal is to make the user look like a multi-dimensional genius."
        )

        # التعليمات: نطلب منه الربط الإبداعي ومنع التكرار
        user_msg = f"""
        User Name: {name}
        Professional Headline: {headline if headline else 'Skill Swapper'}
        Expertise they offer (Teaching): {teach_skills}
        Current curiosities (Learning): {learn_skills}

        Instructions:
        1. Write a 2-sentence bio that is NO LONGER than 30 words.
        2. DO NOT use generic phrases like 'Passionate about' or 'I love to'.
        3. CREATIVE CHALLENGE: Find a clever 'bridge' or 'metaphor' that connects their teaching skills and learning interests.
        4. TONE: Professional yet human and approachable.
        5. VARIETY: Use rare vocabulary. Every time this prompt runs, try a different angle (one time focus on the career, another on the growth, another on the synergy).

        Output only the bio text.
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                # رفع درجة الحرارة لضمان العشوائية والإبداع في كل مرة
                temperature=1.1,
                # منع تكرار الكلمات والأفكار
                presence_penalty=0.8,
                frequency_penalty=0.8,
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Bridging the gap between {teach_skills} and {learn_skills} to create something extraordinary."