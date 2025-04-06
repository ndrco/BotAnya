from translate_utils import translate_prompt_to_english, translate_prompt_to_russian

test_prompt = (
    "<|im_start|>system\nЭто тестовая система. Она задаёт правила поведения.\n<|im_end|>\n"
    "<|im_start|>user\nПривет! *Я сажусь рядом с тобой.* Как ты?\n<|im_end|>\n"
    "<|im_start|>assistant\nПривет! Я рада тебя видеть 😊\n<|im_end|>\n"
)

print("🧾 Test Prompt (Original):\n", test_prompt)

# Переводим на английский
translated_to_english = translate_prompt_to_english(test_prompt)
print("\n🧾 Translated Prompt to English:\n", translated_to_english)

# Переводим обратно на русский
translated_back_to_russian = translate_prompt_to_russian(translated_to_english)
print("\n🧾 Translated Prompt back to Russian:\n", translated_back_to_russian)

