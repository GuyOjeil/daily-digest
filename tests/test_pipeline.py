import sqlite3
import tempfile
import unittest
from pathlib import Path
from src.pipeline import canonical, clean, init_db, store, create_markdown, NOW

class PipelineTests(unittest.TestCase):
    def test_canonical_utm(self):
        self.assertEqual(canonical('https://example.com/a/?utm_source=x&q=1#frag'), 'https://example.com/a?q=1')
    def test_clean_html(self):
        self.assertEqual(clean('<p>Hello <b>world</b></p>'), 'Hello world')
    def test_storage_deduplication(self):
        with sqlite3.connect(':memory:') as con:
            init_db(con)
            item={'title':'Sample release','url':'https://example.com/release','source':'Test','category':'Electronics', 'published':NOW.isoformat(),'summary':'An update'}
            self.assertEqual(store(con,[item,item]),1)
            self.assertEqual(con.execute('SELECT count(*) FROM findings').fetchone()[0],1)
    def test_source_links(self):
        item={'title':'Sample','url':'https://example.com/release','source':'Test','category':'Electronics', 'published':NOW.isoformat(),'summary':'An update'}
        content=create_markdown([item],1,1,'')
        self.assertIn('[Sample](https://example.com/release)', content)
        self.assertIn('## Electronics',content)

class WhatsAppTests(unittest.TestCase):
    def test_message_has_link_and_stories(self):
        from src.dashboard import whatsapp_message
        report={'generated':'2026-11-22T20:00:00+00:00','top':[{'title':'Grid *adds* storage','source':'Utility Dive','category':'Power Systems'}]}
        text=whatsapp_message(report,'https://example.com/#news')
        self.assertIn('https://example.com/#news',text)
        self.assertIn('Grid adds storage (Utility Dive)',text)
        self.assertEqual(whatsapp_message({'generated':'x','top':[]},'https://example.com'),'')

if __name__ == '__main__':
    unittest.main()
