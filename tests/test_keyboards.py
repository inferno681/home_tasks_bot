from bot.keyboards import category_choice_kb


def test_category_choice_kb_includes_top_categories():
    markup = category_choice_kb(["kitchen", "garden"])

    labels = [
        button.text
        for row in markup.inline_keyboard
        for button in row
    ]
    assert "kitchen" in labels
    assert "garden" in labels
