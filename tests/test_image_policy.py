import copy
import unittest
from test_fact_evidence_lifecycle import image_policy, lifecycle, routes_module
from image_fixtures import add_image_plan
from unittest.mock import AsyncMock


class ImagePolicyTests(unittest.TestCase):
    def test_three_required_images_and_two_useful_extras(self):
        fact = add_image_plan({})
        self.assertTrue(image_policy.validate_image_plan(fact))
        for slot in ('cover', 'overview', 'how_it_works'):
            invalid = copy.deepcopy(fact)
            invalid['visual_suggestions'][slot] = ''
            self.assertFalse(image_policy.validate_image_plan(invalid))
        for slot, placement in [('explanation_2','example'),('explanation_3','limits')]:
            fact['visual_suggestions'][slot] = f'A distinct {slot} image.'
            self.assertFalse(image_policy.validate_image_plan(fact))
            fact['image_details'].append({'slot':slot,'placement':placement,'alt':'A useful detail.','caption':'An illustration.','learning_purpose':'Clarify another point.'})
            self.assertTrue(image_policy.validate_image_plan(fact))
        self.assertEqual(len(lifecycle.expected_image_keys(fact['visual_suggestions'])), 5)
        fact['visual_suggestions']['unplanned_sixth'] = 'Another image.'
        self.assertFalse(image_policy.validate_image_plan(fact))

    def test_summary_and_caption_metadata_cannot_be_missing_or_duplicated(self):
        for mutate in (lambda f:f.update(image_details=[]), lambda f:f['image_details'][0].update(placement='example'),
                       lambda f:f['image_details'][1].update(learning_purpose=''), lambda f:f['image_details'].append(f['image_details'][0])):
            fact = add_image_plan({})
            mutate(fact)
            self.assertFalse(image_policy.validate_image_plan(fact))

    def test_myths_keep_the_comparison_pair_and_get_an_overview(self):
        fact = add_image_plan({'myth_statement':'A belief'}, myth=True)
        self.assertTrue(image_policy.validate_image_plan(fact))
        fact['visual_suggestions']['how_it_works'] = 'A further explanation.'
        fact['image_details'].append({'slot':'how_it_works','placement':'explanation','alt':'A mechanism.','caption':'An illustration.','learning_purpose':'Explain the mechanism.'})
        self.assertTrue(image_policy.validate_image_plan(fact))
        self.assertEqual(len(lifecycle.expected_image_keys(fact['visual_suggestions'])), 5)


class ImageWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_images_reach_the_worker_and_partial_status(self):
        routes = routes_module()
        routes.generate_and_save_image = AsyncMock(side_effect=lambda prompt, filename, **kwargs: 'https://example.org/'+filename)
        prompts = {'cover':'Cover','overview':'Summary','how_it_works':'Mechanism','explanation_2':'Example','explanation_3':'Limits'}
        await routes._background_image_task(prompts, 'hash', article={})
        self.assertEqual(routes.generate_and_save_image.await_count, 5)
        state = lifecycle.image_generation_state({'full_response':{'visual_suggestions':prompts},'images':{'cover':'ready','overview':'ready'}},330)
        self.assertEqual(state['status'],'partial')
        self.assertIn('explanation_3',state['failed'])


if __name__ == '__main__': unittest.main()
