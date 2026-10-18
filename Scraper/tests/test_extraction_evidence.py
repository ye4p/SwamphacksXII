"""Offline evidence/date checks; mocked model responses do not measure AI accuracy."""

import json
import os
import unittest
from unittest.mock import patch

from Scraper import gemini_extractor
from Scraper.event_validator import validate_extraction
from test_gatorconnect import event


def validate_flyer(**changes):
    """Use a year in a flyer heading, separate from the printed month/day."""
    text = "FALL 2026 SOCCER SOCIAL Thursday, October 15th Flavet Field 5:00 PM"
    candidate = event(title="Soccer Social", date="2026-10-15",
                      date_text="Thursday, October 15th", time="5:00 PM",
                      location="Flavet Field", city_text=None,
                      supporting_text="October 15th Flavet Field 5:00 PM", Tags=[])
    candidate.update(changes)
    return validate_extraction({"image_text": text, "events": [candidate]}, "")["events"][0]


class EvidenceTests(unittest.TestCase):
    def test_explicit_flyer_year_and_single_quote_pass(self):
        result = validate_flyer()
        self.assertEqual(result["date"], "2026-10-15")
        self.assertEqual(result["validation_status"], "checked")

    def test_different_month_day_or_unprinted_year_removed(self):
        for proposed in ("2026-10-16", "2026-11-15", "2025-10-15", "2026-02-30"):
            with self.subTest(date=proposed):
                self.assertIsNone(validate_flyer(date=proposed)["date"])

    def test_null_date_stays_null_even_with_a_header_year(self):
        # Python checks Gemini's proposed date; it never creates its own date.
        self.assertIsNone(validate_flyer(date=None)["date"])

    @patch('Scraper.event_validator.current_year', return_value=2030)
    def test_missing_source_year_uses_current_year_not_model_guess(self, year):
        candidate = event(date="2026-10-21", date_text="October 21st")
        result = validate_extraction({"image_text": "October 21st Weimer Hall", "events": [candidate]}, "")
        self.assertEqual(result['events'][0]['date'], '2030-10-21')
        self.assertTrue(result['events'][0]['date_year_inferred'])

    @patch('Scraper.event_validator.current_year', return_value=2026)
    def test_year_fallback_handles_written_dates_but_not_vague_or_invalid_dates(self, year):
        for text, expected in [('Wednesday, October 21st', '2026-10-21'),
                               ('Oct 21', '2026-10-21'), ('10/21', '2026-10-21'),
                               ('in the fall', None), ('February 29', None),
                               ('February 30', None), ('October', None)]:
            with self.subTest(text=text):
                result = validate_extraction({'image_text': text, 'events': [
                    event(date=None, date_text=text)]}, '')['events'][0]
                self.assertEqual(result['date'], expected)
                self.assertEqual(result['date_year_inferred'], expected is not None)

    @patch('Scraper.event_validator.current_year', return_value=2028)
    def test_leap_year_and_explicit_year_preservation(self, year):
        result = validate_extraction({'image_text': 'February 29', 'events': [
            event(date=None, date_text='February 29')]}, '')['events'][0]
        self.assertEqual(result['date'], '2028-02-29')
        self.assertEqual(validate_flyer()['date'], '2026-10-15')
        self.assertFalse(validate_flyer()['date_year_inferred'])

    def test_unverified_date_text_does_not_get_a_year(self):
        result = validate_extraction({'image_text': 'Workshop TBA', 'events': [
            event(date=None, date_text='October 21')]}, '')['events'][0]
        self.assertIsNone(result['date'])

    def test_activity_catalog_filtered_but_specific_tba_announcement_survives(self):
        source = ('Host Technical Workshops & Design Team Projects. Organize Professional Events '
                  'including Resume Reviews, Interview Prep, and Industry Networking.')
        candidates = [event(title=title, date=None, date_text=None, time=None,
                            location=None, supporting_text=source, location_kind='missing')
                      for title in ('Technical Workshops', 'Design Team Projects', 'Resume Reviews',
                                    'Interview Prep', 'Industry Networking')]
        self.assertEqual(validate_extraction({'image_text': source, 'events': candidates}, '')['events'], [])
        invitation = 'Join our next Technical Workshops event for Python practice; date TBA.'
        candidates[0]['supporting_text'] = invitation
        result = validate_extraction({'image_text': invitation, 'events': [candidates[0]]}, '')
        self.assertEqual(len(result['events']), 1)

    def test_mixed_post_retains_specific_event_and_drops_explicit_non_events(self):
        source = 'Join the workshop October 21. We also offer resume reviews.'
        candidates = [event(announcement_type='specific_event', date=None, date_text='October 21'),
                      event(announcement_type='general_promotion'), event(announcement_type='recap')]
        result = validate_extraction({'image_text': source, 'events': candidates}, '')
        self.assertEqual(len(result['events']), 1)

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'})
    @patch.object(gemini_extractor, 'extract_image_text', return_value='Host Technical Workshops & Design Team Projects')
    @patch('requests.post')
    @patch('google.genai.Client')
    def test_misclassified_catalog_makes_no_maps_calls(self, client, maps, ocr):
        text = 'Host Technical Workshops & Design Team Projects'
        candidate = event(title='Technical Workshops', date=None, date_text=None, time=None,
                          location=None, supporting_text=text, announcement_type='specific_event')
        generate = client.return_value.__enter__.return_value.models.generate_content
        generate.return_value.text = json.dumps({'image_text': text, 'events': [candidate]})
        result = gemini_extractor.extract_events([(b'\xff\xd8\xff\xd9', 'image/jpeg')], use_cache=False)
        self.assertEqual(result['events'], [])
        maps.assert_not_called()

    def test_persistent_revision_changes_at_new_year(self):
        from Scraper.gatorconnect_pipeline import revision_key
        from test_gatorconnect import post
        with patch('Scraper.gatorconnect_pipeline.current_year', return_value=2026):
            old = revision_key(post())
        with patch('Scraper.gatorconnect_pipeline.current_year', return_value=2027):
            self.assertNotEqual(old, revision_key(post()))

    def test_combined_or_paraphrased_quotes_are_flagged(self):
        for quote in ("SOCCER SOCIAL at Flavet Field", "October 15th ... 5:00 PM"):
            with self.subTest(quote=quote):
                result = validate_flyer(supporting_text=quote)
                self.assertIn("supporting_text: exact excerpt could not be verified.",
                              result["validation_warnings"])

    def test_quote_cannot_cross_caption_ocr_boundary(self):
        result = validate_extraction({"image_text": "Flavet Field", "events": [
            event(supporting_text="Soccer Social Flavet Field")]}, "Soccer Social")
        self.assertIn("supporting_text: exact excerpt could not be verified.",
                      result["events"][0]["validation_warnings"])

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-gemini-key"})
    @patch.object(gemini_extractor, 'extract_image_text', return_value='Officer introductions')
    @patch("requests.post")
    @patch("google.genai.Client")
    def test_prompt_contract_and_empty_classification_skip_maps(self, client, maps, ocr):
        # Inspect what is sent to Gemini without making a model request. Actual
        # officer/recap classification quality still requires a live sample.
        generate = client.return_value.__enter__.return_value.models.generate_content
        generate.return_value.text = json.dumps({"image_text": "Officer introductions", "events": []})
        result = gemini_extractor.extract_events([(b"\xff\xd8\xff\xd9", "image/jpeg")],
                                                 "Meet our officers!", use_cache=False)
        instructions = generate.call_args.kwargs["config"].system_instruction
        for required in ("GBM in the fall", "date TBA", "recap", "SAME flyer",
                         "2026-10-15", "ONE contiguous verbatim", "unrelated officer bios"):
            self.assertIn(required, instructions)
        self.assertEqual(result["events"], [])
        maps.assert_not_called()


if __name__ == "__main__":
    unittest.main()
