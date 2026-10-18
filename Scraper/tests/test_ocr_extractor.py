"""Offline OCR transport and text-only Gemini integration checks."""
import json
import os
import unittest
from io import BytesIO
import random
from unittest.mock import patch

import requests
from PIL import Image

from Scraper import gemini_extractor, ocr_extractor
from Scraper.runtime_utils import ScraperError

IMAGE = (b'\xff\xd8\xff\xd9', 'image/jpeg')


def payload(text):
    return {"OCRExitCode": 1, "IsErroredOnProcessing": False,
            "ParsedResults": [{"FileParseExitCode": 1, "ParsedText": text}]}


class CompressionTests(unittest.TestCase):
    def test_small_original_is_unchanged(self):
        self.assertEqual(ocr_extractor.prepare_ocr_image(*IMAGE), IMAGE)

    def test_large_png_fits_and_decodes_as_jpeg(self):
        pixels = random.Random(42).randbytes(1400 * 1000 * 3)
        source = Image.frombytes('RGB', (1400, 1000), pixels)
        buffer = BytesIO()
        source.save(buffer, format='PNG')
        original = buffer.getvalue()
        self.assertGreater(len(original), 1_000_000)
        compressed, mime = ocr_extractor.prepare_ocr_image(original, 'image/png')
        self.assertLess(len(compressed), 1_000_000)
        self.assertEqual(mime, 'image/jpeg')
        with Image.open(BytesIO(compressed)) as result:
            result.load()
            self.assertEqual(result.size, source.size)

    def test_resize_when_quality_alone_cannot_fit(self):
        source = Image.frombytes('RGB', (800, 600), random.Random(7).randbytes(800 * 600 * 3))
        buffer = BytesIO()
        source.save(buffer, format='PNG')
        with patch.object(ocr_extractor, 'OCR_MAX_BYTES', 50_000):
            compressed, _ = ocr_extractor.prepare_ocr_image(buffer.getvalue(), 'image/png')
        self.assertLess(len(compressed), 50_000)
        with Image.open(BytesIO(compressed)) as result:
            self.assertLess(result.width, 800)
            self.assertAlmostEqual(result.width / result.height, 800 / 600, places=2)

    def test_transparent_webp_becomes_white_jpeg(self):
        buffer = BytesIO()
        Image.new('RGBA', (100, 100), (0, 0, 0, 0)).save(buffer, format='WEBP', lossless=True)
        compressed, mime = ocr_extractor.prepare_ocr_image(buffer.getvalue(), 'image/webp')
        self.assertEqual(mime, 'image/jpeg')
        with Image.open(BytesIO(compressed)) as result:
            self.assertEqual(result.getpixel((50, 50)), (255, 255, 255))


@patch.dict(os.environ, {"OCR_SPACE_API_KEY": "test-ocr", "GEMINI_API_KEY": "test-gemini"})
class OCRTests(unittest.TestCase):
    @patch('requests.post')
    def test_carousel_uploads_and_order(self, post):
        response = post.return_value.__enter__.return_value
        response.status_code = 200
        response.json.side_effect = [payload('Workshop'), payload('October 21')]
        text = ocr_extractor.extract_image_text([IMAGE, IMAGE])
        self.assertEqual(text, 'Image 1:\nWorkshop\n\nImage 2:\nOctober 21')
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs['headers'], {'apikey': 'test-ocr'})
        self.assertEqual(post.call_args.kwargs['files']['file'][1], IMAGE[0])

    @patch('requests.post')
    def test_rejects_failures_and_partial_results(self, post):
        response = post.return_value.__enter__.return_value
        response.status_code = 200
        for result in ({'OCRExitCode': 2}, {'IsErroredOnProcessing': True}, [],
                       {'OCRExitCode': 1, 'ParsedResults': []}):
            response.json.return_value = result
            with self.assertRaises(ScraperError):
                ocr_extractor.extract_image_text([IMAGE])

    @patch('requests.post')
    def test_size_and_format_checked_before_upload(self, post):
        for invalid in ((b'x' * 1_000_001, 'image/jpeg'), (b'webp', 'image/webp')):
            with self.assertRaises(ScraperError):
                ocr_extractor.extract_image_text([IMAGE, invalid])
        post.assert_not_called()

    @patch('requests.post', side_effect=requests.Timeout('secret details'))
    def test_timeout_has_safe_error(self, post):
        with self.assertRaises(ScraperError) as caught:
            ocr_extractor.extract_image_text([IMAGE])
        self.assertEqual(caught.exception.code, 'timeout')
        self.assertNotIn('secret', str(caught.exception))

    @patch('requests.post')
    def test_missing_key(self, post):
        with patch.dict(os.environ, {'OCR_SPACE_API_KEY': ''}):
            with self.assertRaises(ScraperError):
                ocr_extractor.extract_image_text([IMAGE])
        post.assert_not_called()

    @patch('google.genai.Client')
    @patch.object(gemini_extractor, 'extract_image_text', return_value='Image 1:\nWorkshop')
    def test_gemini_receives_only_text_and_original_ocr_is_preserved(self, ocr, client):
        generate = client.return_value.__enter__.return_value.models.generate_content
        generate.return_value.text = json.dumps({'image_text': 'invented text', 'events': []})
        result = gemini_extractor.extract_events([IMAGE], 'Join us!', enrich=False, use_cache=False)
        contents = generate.call_args.kwargs['contents']
        self.assertTrue(all(isinstance(part, str) for part in contents))
        self.assertIn('Image 1:\nWorkshop', contents[0])
        self.assertIn('Join us!', contents[1])
        self.assertEqual(result['image_text'], 'Image 1:\nWorkshop')

    @patch('google.genai.Client')
    @patch.object(gemini_extractor, 'extract_image_text', side_effect=ScraperError('ocr', 'failed', 'OCR failed.'))
    def test_ocr_failure_stops_gemini(self, ocr, client):
        with self.assertRaises(ScraperError):
            gemini_extractor.extract_events([IMAGE], enrich=False, use_cache=False)
        client.assert_not_called()
