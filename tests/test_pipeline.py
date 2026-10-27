import base64
import json
import unittest
from unittest.mock import patch
import server


def review(errors=0):
    return {'error_count':errors,'evaluated_words':100,'issues':['Fix words'] if errors else []}

class PipelineTests(unittest.TestCase):
    def test_scoring(self):
        self.assertEqual(server.review_metrics(review())['agreement'],100)
        self.assertEqual(server.review_metrics(review(3))['agreement'],97)
        self.assertEqual(server.review_metrics(review(110))['agreement'],0)
        self.assertTrue(server.review_metrics(review(2))['accepted'])
        self.assertFalse(server.review_metrics(review(3))['accepted'])
        self.assertFalse(server.review_metrics(review(), 'hello world','hello there')['accepted'])

    def test_invalid_review(self):
        for invalid in [{**review(),'evaluated_words':0},{**review(),'error_count':-1},{**review(),'issues':'none'}, {**review(),'corrected_transcript':'hello world'}, {**review(),'error_count':1,'issues':[]}]:
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
        self.assertNotIn('corrected_transcript',str(job))
        first_review_prompt = json.loads(agent.call_args_list[1].args[2])
        self.assertNotIn('corrected_transcript', first_review_prompt['output_schema'])
        self.assertIn('Never write', agent.call_args_list[1].args[1])
        rework_prompt = json.loads(agent.call_args_list[2].args[2])
        self.assertEqual(rework_prompt['draft'], 'hello there')
        self.assertEqual(rework_prompt['review_feedback']['reviewer_feedback'],review(3))
        self.assertEqual(job['results'][0]['history'][1]['transcript'], 'hello world')

    def test_rejects_mixed_agent_roles(self):
        for replies in [
            [{'transcript':'hello world','error_count':0}],
            [{'transcript':'hello world'}, {**review(),'corrected_transcript':'hello world'}],
        ]:
            server.JOBS['mixed']={'status':'running','results':[]}
            with patch.object(server,'stt',return_value='draft'),patch.object(server,'agent',side_effect=replies):
                server.run_job('mixed',self.payload())
            self.assertEqual(server.JOBS['mixed']['status'],'failed')
            self.assertEqual(server.JOBS['mixed']['results'],[])

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

    def test_provider_validation(self):
        p=self.payload()
        p['providers'][0]={**p['providers'][0],'kind':'azure','model':''}
        server.validate(p)  # Azure may omit the model field (locales optional)
        p['providers'][1]={**p['providers'][1],'kind':'deepgram','model':''}
        with self.assertRaises(ValueError):server.validate(p)  # Deepgram needs a model
        p['providers'][1]={**p['providers'][1],'model':'nova-3'}
        server.validate(p)  # different kinds with same url are distinct providers
        p['providers'][1]={**p['providers'][1],'kind':'unknown-api'}
        with self.assertRaises(ValueError):server.validate(p)


class FakeResponse:
    def __init__(self, payload): self.payload=payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.payload).encode()

class SttAdapterTests(unittest.TestCase):
    def call(self, kind, reply, model='m'):
        captured={}
        def fake_urlopen(req, timeout=None):
            captured['req']=req
            return FakeResponse(reply)
        with patch.object(server,'urlopen',side_effect=fake_urlopen):
            text=server.stt({'kind':kind,'url':'https://api.example.com/stt','model':model,'key':'test-secret'},'clip.mp3',b'AUDIO')
        req=captured['req']
        headers={k.lower():v for k,v in req.header_items()}
        self.assertNotIn('test-secret',str(text))
        return text,req,headers

    def test_openai_adapter(self):
        text,req,headers=self.call('openai',{'text':'openai text'})
        self.assertEqual(text,'openai text')
        self.assertEqual(headers['authorization'],'Bearer test-secret')
        self.assertIn('multipart/form-data',headers['content-type'])
        self.assertIn(b'name="model"',req.data) and self.assertIn(b'AUDIO',req.data)

    def test_deepgram_adapter(self):
        text,req,headers=self.call('deepgram',{'results':{'channels':[{'alternatives':[{'transcript':'dg text'}]}]}},model='nova-3')
        self.assertEqual(text,'dg text')
        self.assertEqual(headers['authorization'],'Token test-secret')
        self.assertEqual(headers['content-type'],'audio/mpeg')
        self.assertEqual(req.data,b'AUDIO')
        self.assertIn('model=nova-3',req.full_url)

    def test_elevenlabs_adapter(self):
        text,req,headers=self.call('elevenlabs',{'text':'el text'},model='scribe_v1')
        self.assertEqual(text,'el text')
        self.assertEqual(headers['xi-api-key'],'test-secret')
        self.assertIn(b'name="model_id"',req.data) and self.assertIn(b'AUDIO',req.data)

    def test_azure_adapter(self):
        text,req,headers=self.call('azure',{'combinedPhrases':[{'text':'line one'},{'text':'line two'}]},model='en-US,hi-IN')
        self.assertEqual(text,'line one\nline two')
        self.assertEqual(headers['ocp-apim-subscription-key'],'test-secret')
        self.assertIn(b'name="definition"',req.data) and self.assertIn(b'hi-IN',req.data) and self.assertIn(b'name="audio"',req.data)

    def test_unknown_kind_and_empty_text(self):
        with self.assertRaises(ValueError):
            with patch.object(server,'urlopen',return_value=FakeResponse({'text':'ok'})):
                server.stt({'kind':'other','url':'https://api.example.com','model':'m','key':'k'},'clip.mp3',b'AUDIO')
        with self.assertRaises(ValueError):
            with patch.object(server,'urlopen',return_value=FakeResponse({'results':{'channels':[]}})):
                server.stt({'kind':'deepgram','url':'https://api.example.com','model':'m','key':'k'},'clip.mp3',b'AUDIO')

if __name__=='__main__':unittest.main()
