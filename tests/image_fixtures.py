"""Small valid article-image plans for offline provider tests."""
def add_image_plan(fact, myth=False):
    keys = ['cover', 'overview', 'myth_visual', 'truth_visual'] if myth else ['cover', 'overview', 'how_it_works']
    fact['visual_suggestions'] = {key: f'An independent {key} illustration.' for key in keys}
    fact['image_details'] = [{'slot':key, 'placement':'overview' if key == 'overview' else 'explanation',
        'alt':f'{key} illustration', 'caption':'An explanatory illustration.', 'learning_purpose':f'Explain the {key} idea.'} for key in keys if key != 'cover']
    return fact
