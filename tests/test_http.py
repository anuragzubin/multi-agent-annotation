import json
import threading
import time
import unittest
from urllib.request import urlopen, Request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import server
import test_pipeline

class HttpTests(unittest.TestCase):
    def test_http_submission_to_results(self):
        http = ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{http.server_port}'
        try:
            with urlopen(base+'/api/health') as response:
                self.assertEqual(json.load(response),{'status':'ok'})
            with urlopen(base+'/') as response:
                self.assertIn('Better transcripts, together.',response.read().decode())
            with patch.object(server,'stt',return_value='hello world'),patch.object(server,'agent',side_effect=[{'transcript':'hello world'},test_pipeline.review()]*2):
                req=Request(base+'/api/jobs',data=json.dumps(test_pipeline.PipelineTests().payload()).encode(),headers={'Content-Type':'application/json'})
                with urlopen(req) as response:
                    self.assertEqual(response.status,202)
                    job_id=json.load(response)['id']
                for _ in range(100):
                    with urlopen(base+'/api/jobs/'+job_id) as response:
                        job=json.load(response)
                    if job['status']!='running':break
                    time.sleep(.01)
                self.assertEqual(job['status'],'complete')
                self.assertEqual(len(job['results']),2)
                self.assertTrue(all(r['accepted'] for r in job['results']))
                self.assertNotIn('test-secret',json.dumps(job))
        finally:
            http.shutdown()
            http.server_close()
