# Accord Annotation Studio

A two-source audio annotation tool with a transcriber agent and an independent reviewer agent. Python 3.12+; no third-party runtime dependencies.

## Run

```sh
cd /workspace/multi-agent-annotation
python server.py
```

The server binds to 127.0.0.1:8000 by default. Set `HOST` and `PORT` to change this. This is a single-user development tool: use trusted access controls before exposing it to other users. Jobs and credentials are held in process memory, not on disk. Restarting loses results; export JSON first. Provider calls may take up to 180 seconds each. No automatic API retries are made to avoid duplicate billing.

## Workflow

1. Upload 1–10 MP3/WAV files (20 MB each, 45 MB total). Short clips work best with audio-model context limits.
2. Enter guidelines, and optionally a trusted reference transcript for each file.
3. Configure two STT endpoints, models and API keys. Defaults are OpenAI and Groq examples; you must provide credentials and confirm model availability.
4. Expand **Agent configuration** and configure transcriber and reviewer models/keys. Both must support OpenAI Chat Completions `input_audio` content (MP3/WAV) and return text containing JSON. `gpt-audio` is an editable example, not a verified binding. Text-only models cannot review the audio and will fail.
5. Start annotation. Each STT draft is independently transcribed by the Transcriber, then audited by the Reviewer. The Transcriber alone writes and corrects transcripts. The Reviewer only returns issue locations, actionable feedback and error counts; it never generates replacement transcript text. Reviewer errors above 2% trigger rework with feedback. Each submission has its own cycle history and limit (1–10). A limit hit stays flagged; it is never silently approved. Both sources are reviewed for every file unless an API fails, in which case completed results remain available.
6. Compare both submissions and export results as JSON.

Custom STT APIs must accept multipart `file`, `model`, `response_format=json` and return `{"text":"..."}`. Agent APIs must accept OpenAI-compatible Chat Completions messages with inline audio and return `choices[0].message.content`. Arbitrary vendor-specific request formats require adapters. All configured APIs must use HTTPS. Keys are only sent by the server to the entered endpoint; enter trusted endpoints. The browser does not persist keys in local storage. Audio is shared with the selected STT provider and both agent endpoints. Runtime network policy must allow their hostnames, such as `api.openai.com` and `api.groq.com`.

## Scores and acceptance

- **Reviewer estimate**: reviewer-counted word and guideline defects / audited word count × 100. This is an AI judgment, not a certified accuracy measurement.
- **Reference WER**, when supplied: word-level Levenshtein distance from trusted reference to submission / reference words × 100. Case and punctuation are ignored; guideline issues are still audited separately.
- **Acceptance**: reviewer estimate ≤ 2%, and reference WER ≤ 2% if available. Comparison uses the unrounded rate.
- **Transcriber–reviewer agreement**: max(0, 100 − reviewer-estimated error percentage). The dashboard averages final-cycle scores across completed submissions. This is reviewer-assessed agreement, not an independent accuracy measurement. Reference WER remains a separate acceptance check.

Each cycle shows the Transcriber’s submitted transcript and the Reviewer’s feedback separately. Review responses containing a transcript or extra fields are rejected. Reviewer feedback is passed to the next transcriber cycle. The reviewer listens independently but shares the same guidelines, and may use a different provider/model for greater independence. Model mistakes remain possible. There is no guarantee of convergence; the cycle cap limits cost. Live API behavior requires real credentials/audio and is not covered by mocked tests.

## Validation

```sh
python -m unittest discover -s tests -v
node --check static/app.js
```

Tests cover threshold boundaries, agreement, measured WER, rework feedback, both STT submissions, maximum-cycle handling, provider errors, and input validation. The app has no database, background queue, production authentication or vendor-specific adapters.

## Public live-test deployment

The included Dockerfile works on a container hosting service. Build with `docker build -t accord .` and run with `docker run --rm -p 8000:8000 accord`. Hosting platforms can set `PORT`; `HOST=0.0.0.0` is already configured in the image. Set the health-check path to `/api/health`. Use a single instance because job state is in memory. Use the hosting service's HTTPS URL.

This is a single-user live-test build, not a multi-user production deployment. There is no account system; anyone with the URL can open the tool, and job URLs give access to their results. Do not embed API keys in the image or hosting configuration: enter your own keys in the UI. Results disappear on restart. A public deployment requires a hosting account and deployment authorization; publishing a Codex environment snapshot does not expose an app publicly.
