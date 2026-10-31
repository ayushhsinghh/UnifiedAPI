"""Article image contract: cover, overview/card image and explanatory images."""
IMAGE_KEYS = ('cover', 'overview', 'how_it_works', 'explanation_2', 'explanation_3', 'explanation_4', 'explanation_5', 'explanation_6', 'myth_visual', 'truth_visual')
IMAGE_INSTRUCTIONS = """
ARTICLE IMAGE PLAN (overrides older cover-only or single-supporting-image instructions):
Every article requires 3-5 generated images: cover, overview, and at least one explanatory image.
For ordinary articles and category lessons, fill cover, overview and how_it_works prompts.
Use explanation_2 and explanation_3 only if they explain additional useful points. Otherwise leave empty.
For myth articles, fill cover, overview, myth_visual and truth_visual; keep the comparison pair.
A myth article may also request how_it_works if useful, for a maximum of five images total.
The overview is a standalone visual summary of the whole fact, also used as the discovery card image.
Make it readable at thumbnail size with a centered subject and a different composition from the cover.
The cover fills the screen: subject near center-right inside the central 60%, quiet left third for title,
generous crop margins, one coherent scene. Do not render words, labels, numbers or fake writing.
Explanatory images illustrate concrete situations, structures, apparatus or mechanisms, not filler.
Structured scientific/legal diagrams remain separate and are not replaced by generated art.
Write an independent, concrete prompt for each requested image. No 'same as above' references.
Keep the article's visual style coherent. Never invent measurements, evidence or authentic documents.
Return image_details for EVERY non-cover requested slot, exactly once: slot, placement, alt, caption,
learning_purpose. overview placement is overview; how_it_works/myth_visual/truth_visual use explanation.
Optional explanation_2/explanation_3 use explanation, example or limits, whichever best matches the content.
Keep captions and alt text concise. Mark conceptual illustrations or reconstructions as such when needed.
Set legacy supporting_image to null in category lessons. Use image_details for the full image plan.
"""


def validate_image_plan(fact, myth=None):
    if fact.get('article_type') in ('india_lesson','food_lesson','fashion_lesson','geography_lesson'):
        from .india import validate_india_images
        return validate_india_images(fact)
    if fact.get('article_type') == 'country_profile':
        from .country import validate_country_images
        return validate_country_images(fact)
    if myth is None:
        myth = 'myth_statement' in fact
    visuals, details = fact.get('visual_suggestions'), fact.get('image_details')
    if not isinstance(visuals, dict) or not isinstance(details, list):
        return False
    if any(not isinstance(value, str) for value in visuals.values()):
        return False
    active = {key for key, value in visuals.items() if value.strip()}
    required = {'cover', 'overview', 'myth_visual', 'truth_visual'} if myth else {'cover', 'overview', 'how_it_works'}
    allowed = required | ({'how_it_works'} if myth else {'explanation_2', 'explanation_3'})
    if not required <= active or not active <= allowed or not 3 <= len(active) <= 5:
        return False
    if len(details) != len(active) - 1 or any(not isinstance(item, dict) for item in details):
        return False
    slots = [item.get('slot') for item in details]
    if any(not isinstance(slot, str) for slot in slots) or len(set(slots)) != len(slots) or set(slots) != active - {'cover'}:
        return False
    for item in details:
        if any(not isinstance(item.get(key), str) or not item[key].strip() or len(item[key]) > 1200 for key in ('alt', 'caption', 'learning_purpose')):
            return False
        placement = item.get('placement')
        expected = 'overview' if item['slot'] == 'overview' else 'explanation'
        if item['slot'] in ('explanation_2', 'explanation_3'):
            if placement not in ('explanation', 'example', 'limits'):
                return False
        elif placement != expected:
            return False
    return True
