import base64
import unittest
from unittest.mock import patch
import server


def review(errors=0):
    return {'corrected_transcript':'hello world','error_count':errors,'evaluated_words':100,'issues':['Fix words'] if errors else []}

class PipelineTests(unittest.TestCase):
    def test_scoring(self):
        self.assertEqual(server.agreement('Hello, world!', 'hello world'),100)
        self.assertEqual(server.agreement('hello there','hello world'),50)
        self.assertTrue(server.review_metrics(review(2))['accepted'])
        self.assertFalse(server.review_metrics(review(3))['accepted'])
        self.assertFalse(server.review_metrics(review(), 'hello world','hello there')['accepted'])

    def test_invalid_review(self):
        for invalid in [{**review(),'evaluated_words':0},{**review(),'error_count':-1},{**review(),'issues':'none'}]:
            with self.assertRaises(ValueError):server.review_metrics(invalid)

    def payload(self):
        conf={'url':'https://example.com/api','key':'test-secret','model':'audio-model'}
        return {'files':[{'name':'test.wav','data':base64.b64encode(b'audio').decode()}], 'providers':[conf,{**conf,'model':'other'}], 'transcriber':conf,'reviewer':conf,'guidelines':'Verbatim','max_cycles':3}

    def test_rework_and_both_providers(self):
        p=self.payload();server.validate(p)
        server.JOBS['test']={'status':'running','results':[]}
        replies=[{'transcript':'hello there'},review(3),{'transcript':'hello world'},review(),{'transcript':'hello world'},review()]
        with patch.object(server,'stt',return_value='hello draft') as stt, patch.object(server,'agent',side_effect=replies) as agent:
            server.run_job('test',p)
        job=server.JOBS['test']
        self.assertEqual(job['status'],'complete')
        self.assertEqual(stt.call_count,2)
        self.assertEqual([len(r['history']) for r in job['results']],[2,1])
        self.assertTrue(all(r['accepted'] for r in job['results']))
        self.assertIn('Fix words',agent.call_args_list[2].args[2])
        self.assertNotIn('test-secret',str(job))

    def test_limit_keeps_flagged(self):
        p=self.payload();p['max_cycles']=1
        server.JOBS['limit']={'status':'running','results':[]}
        with patch.object(server,'stt',return_value='draft'),patch.object(server,'agent',side_effect=[{'transcript':'bad'},review(4)]*2):
            server.run_job('limit',p)
        self.assertEqual(server.JOBS['limit']['status'],'complete')
        self.assertTrue(all(not r['accepted'] for r in server.JOBS['limit']['results']))

    def test_provider_failure(self):
        server.JOBS['failure']={'status':'running','results':[]}
        with patch.object(server,'stt',side_effect=ValueError('Provider returned HTTP 401')):
            server.run_job('failure',self.payload())
        self.assertEqual(server.JOBS['failure']['status'],'failed')

    def test_validation(self):
        p=self.payload();p['files'][0]['name']='test.exe'
        with self.assertRaises(ValueError):server.validate(p)

if __name__=='__main__':unittest.main()
