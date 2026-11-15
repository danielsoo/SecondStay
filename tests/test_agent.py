"""Synthetic buildings only; scripted models exercise the real deepagents graph offline."""
import json
from dataclasses import asdict

import pytest

from secondstay import agent, web, vexcel
from secondstay.checklist import NOTICE, ISSUE
from secondstay.costar import Building, Scan


@pytest.fixture
def review(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'SCAN_CACHE', tmp_path / 'scans')
    monkeypatch.setattr(web, 'OUTSIDE_CACHE', tmp_path / 'outside')
    monkeypatch.setattr(web, 'STREET_CACHE', tmp_path / 'streets')
    monkeypatch.setenv('SECONDSTAY_OFFLINE', '1')
    monkeypatch.delenv('MATTERPORT_TOKEN_ID', raising=False)
    monkeypatch.delenv('VEXCEL_API_KEY', raising=False)
    b = Building(1, name='Synthetic building', year_built=1990, stories=3,
                 zone_recorded='C2', rentable_sqft=12000, scans=[Scan('SAMPLE0001')])
    return agent.Review(b, directory=tmp_path / 'runs', mode='test')


def collect(review):
    for action in ('inspect_gaps', 'read_record', 'read_scan', 'read_outside', 'read_streets', 'cross_check'):
        review.execute(action)


def test_review_requires_gathering_and_rechecks_after_changes(review):
    assert 'error' in review.execute('write_review')
    collect(review)
    review.execute('read_record')
    assert review.execute('write_review')['remaining'] == ['cross_check']
    review.execute('cross_check')
    assert review.execute('write_review')['recorded']
    result = review.data['result']
    assert len(result['rows']) == 14 and sum(result['counts'].values()) == 14
    assert result['image_readings'] == {'panoramas': None, 'plan': None}
    assert NOTICE in review.data['report']
    assert not agent.BANNED.search(review.data['report'].replace(NOTICE, ''))
    stored = json.loads((review.directory / (review.data['id'] + '.json')).read_text())
    assert stored['status'] == 'completed'
    assert 'score' not in result


def test_suite_scope_rejects_unrelated_scan(review):
    review.building.spaces = [{'id': 9, 'sqft': 1000, 'scans': []}]
    with pytest.raises(ValueError):
        agent.Review(review.building, '9', 'SAMPLE0001', directory=review.directory)
    with pytest.raises(ValueError):
        agent.Review(review.building, '999', directory=review.directory)
    with pytest.raises(ValueError):
        agent.Review(review.building, scan_id='../../secret', directory=review.directory)
    scoped = agent.Review(review.building, '9', directory=review.directory)
    assert scoped.scan_id == ''
    assert 'unavailable' in scoped.execute('read_plan')
    scoped.execute('read_record')
    assert scoped.facts.space_sqft == 1000


def test_disagreement_requires_rereading_and_remains_visible(review, monkeypatch):
    monkeypatch.setattr(web, 'read_outside', lambda b: vexcel.Outside(height_ft=160, footprint=[[(0, 0), (1, 0), (0, 1)]], bbox=[0, 0, 1, 1]))
    monkeypatch.setattr(web, 'read_streets', lambda *args: [])
    collect(review)
    assert review.conflicts
    assert 'error' in review.execute('write_review')
    review.execute('read_record')
    review.execute('read_outside')
    review.execute('cross_check')
    review.execute('write_review')
    height = next(r for r in review.data['result']['rows'] if r['key'] == 'height')
    assert height['state'] == ISSUE and '8–25' in height['evidence']


def test_provider_errors_do_not_leak_credentials(review, monkeypatch):
    def broken(*args):
        raise RuntimeError('secret-key-in-signed-url')
    monkeypatch.setattr(web, 'read_scan', broken)
    result = review.execute('read_scan')
    assert result['error_type'] == 'RuntimeError'
    assert 'secret-key' not in json.dumps(review.data)


def test_missing_model_settings_are_explicit(monkeypatch):
    monkeypatch.delenv('SECONDSTAY_AGENT_MODEL', raising=False)
    assert not agent.configuration()['ready']
    assert 'SECONDSTAY_AGENT_MODEL' in agent.configuration()['message']


def test_openai_needs_only_its_own_key(monkeypatch):
    for prefix in ('SECONDSTAY_AGENT', 'SECONDSTAY_VISION'):
        monkeypatch.setenv(prefix + '_PROVIDER', 'openai')
        monkeypatch.setenv(prefix + '_MODEL', 'test-model')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    assert agent.model_settings() == ('openai', 'test-model', 'sk-test')
    assert agent.model_settings(vision=True)[0] == 'openai'  # one key covers reasoning and images
    model = agent.chat_model()
    assert type(model).__name__ == 'ChatOpenAI' and 'openrouter' not in str(model.openai_api_base or '')


def test_cache_replay_rejects_path_traversal_and_marks_stale_runs(review):
    with pytest.raises(ValueError):
        agent.load_run('../outside', review.directory)
    assert agent.load_run(review.data['id'], review.directory)['status'] == 'interrupted'


def test_real_deepagents_tool_loop_and_invalid_argument_recovery(review):
    pytest.importorskip('deepagents')
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    class Scripted(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    actions = ['not_a_tool', 'inspect_gaps', 'read_record', 'read_scan', 'read_outside',
               'read_streets', 'cross_check', 'write_review']
    replies = [AIMessage(content='', tool_calls=[{'name': 'evidence_step', 'args': {'action': action},
                                                  'id': str(i), 'type': 'tool_call'}]) for i, action in enumerate(actions)]
    replies.append(AIMessage(content='Recorded.'))
    result = agent.run_review(review, Scripted(responses=replies))
    assert result['status'] == 'completed', result['events'][-1]
    assert result['mode'] == 'test'
    assert 'not_a_tool' not in review.calls
    assert sum(result['result']['counts'].values()) == 14


def test_model_that_stops_early_does_not_create_fake_report(review):
    pytest.importorskip('deepagents')
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    class Scripted(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self
    result = agent.run_review(review, Scripted(responses=[AIMessage(content='Done')]))
    assert result['status'] == 'incomplete' and result['result'] is None
    assert 'report' not in result


@pytest.mark.parametrize('override', [{'stairs': -1}, {'stairs': True}, {'with_windows': 8}, {'notes': 'approved'}, {'extra': 'unexpected'}])
def test_vision_rejects_bad_observations(monkeypatch, override):
    pytest.importorskip('langchain_core')
    from langchain_core.messages import AIMessage
    from PIL import Image
    import io
    data = {'stairs': 1, 'notes': 'Partial views.', 'panoramas': 2, 'with_windows': 1,
            'exit_doors': 1, 'indoor': True, 'space': 'office'} | override
    class Vision:
        def invoke(self, messages):
            return AIMessage(content=json.dumps(data))
    monkeypatch.setattr(agent, 'chat_model', lambda **kwargs: Vision())
    image = io.BytesIO()
    Image.new('RGB', (8, 8)).save(image, format='PNG')
    with pytest.raises(ValueError):
        agent.read_vision(image.getvalue(), 'panoramas')


def test_new_plan_reading_has_correct_source(review):
    review.facts.plan_reading = {'stairs': 2, 'elevators': 1, 'covers': 'part', 'source': 'Matterport'}
    row = next(r for r in review.rows() if r.key == 'exits')
    assert row.layer == 'Matterport floor plan, read by an AI model'
    assert 'read from images' in row.evidence.lower()


def test_http_review_routes_validate_origin_scope_and_replay(review, monkeypatch):
    from http.server import ThreadingHTTPServer
    import threading
    import urllib.request
    import urllib.error
    monkeypatch.setattr(agent, 'RUN_DIR', review.directory)
    monkeypatch.setattr(web.Handler, 'buildings', {1: review.building})
    server = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        request = urllib.request.Request(base + '/api/spaces/1/reviews', data=b'{}',
                                         headers={'Content-Type': 'application/json', 'Origin': 'https://example.com'})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 403
        with urllib.request.urlopen(base + '/api/reviews/' + review.data['id']) as response:
            assert json.load(response)['id'] == review.data['id']
        with urllib.request.urlopen(base + '/api/spaces/1/reviews') as response:
            assert len(json.load(response)['runs']) == 1
        collect(review)
        review.execute('write_review')
        with urllib.request.urlopen(base + '/api/reviews/' + review.data['id'] + '/report.md') as response:
            assert NOTICE in response.read().decode()
    finally:
        server.shutdown()
        server.server_close()


def test_city_records_feed_the_agent_checklist(review, monkeypatch):
    from secondstay import evidence
    assert 'unavailable' in review.execute('read_city_records')  # nothing cached for a synthetic parcel
    loaded = ({'topics': {'sprinklers': {'count': 3}}, 'stairs_named': 2}, {'zoning': [{'zone': 'C2-1'}]}, None)
    seen = []
    monkeypatch.setattr(evidence, 'load', lambda b: loaded)
    monkeypatch.setattr(evidence, 'apply', lambda rows, facts, s, r, space=None, plans=None: seen.append((s, r)) or rows)
    out = review.execute('read_city_records')
    assert out['permits_by_topic'] == {'sprinklers': 3} and out['zoning_map'] == [{'zone': 'C2-1'}]
    review.execute('inspect_gaps')
    assert seen and seen[-1] == loaded[:2]  # the checklist the agent records includes the city evidence


def test_lead_delegates_to_two_specialists_through_the_real_graph(review, monkeypatch):
    pytest.importorskip('deepagents')
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from secondstay import evidence

    class Scripted(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            seen_tools.append({t.name if hasattr(t, 'name') else t.get('name') for t in tools})
            return self

    seen_tools = []
    monkeypatch.setattr(evidence, 'load', lambda b: ({'topics': {'sprinklers': {'count': 3}}}, {'zoning': []}, None))
    call = lambda name, args, i: AIMessage(content='', tool_calls=[{'name': name, 'args': args, 'id': f'c{i}', 'type': 'tool_call'}])
    script = [call('evidence_step', {'action': a}, i) for i, a in
              enumerate(['inspect_gaps', 'read_record', 'read_scan', 'read_outside', 'read_streets'])]
    script += [call('task', {'description': 'Read the city records for this parcel.', 'subagent_type': 'city-records-reader'}, 10),
               call('city_step', {'action': 'read_city_records'}, 11), AIMessage(content='Three sprinkler permits on record.'),
               call('task', {'description': 'Read the plan image for stairs.', 'subagent_type': 'image-reader'}, 20),
               call('image_step', {'action': 'read_plan'}, 21), AIMessage(content='No image offline.'),
               call('evidence_step', {'action': 'read_city_records'}, 30),  # the lead cannot read delegated sources itself
               call('evidence_step', {'action': 'cross_check'}, 31), call('evidence_step', {'action': 'write_review'}, 32),
               AIMessage(content='Recorded.')]
    result = agent.run_review(review, Scripted(responses=script))
    assert result['status'] == 'completed', result['events'][-1]
    by = {(e['action'], e['by']) for e in result['events'] if e.get('stage') == 'started'}
    assert ('read_city_records', 'city-records-reader') in by and ('read_plan', 'image-reader') in by
    assert ('read_city_records', 'lead') not in by
    for tools in seen_tools:  # neither the lead nor a specialist can reach files or a shell
        assert not tools & {'ls', 'read_file', 'write_file', 'edit_file', 'glob', 'grep', 'execute'}
    assert any('task' in t and 'evidence_step' in t for t in seen_tools)
    assert any(t >= {'city_step'} and 'task' not in t for t in seen_tools)


def test_streets_read_before_the_footprint_do_not_count(review):
    review.execute('read_streets')
    assert 'read_streets' not in {k for k, v in review.calls.items() if v}
    for action in ('inspect_gaps', 'read_record', 'read_scan', 'read_outside', 'cross_check'):
        review.execute(action)
    assert 'read_streets' in review.execute('write_review').get('remaining', [])


def test_run_history_lists_newest_first_with_the_requested_scan_first(tmp_path):
    def write(i, scan, at, status='completed', building=1, space=''):
        run = {'id': f'{i:032x}', 'building_id': building, 'space_id': space, 'scan_id': scan,
               'status': status, 'mode': 'live', 'started_at': at, 'events': []}
        (tmp_path / f'{i:032x}.json').write_text(json.dumps(run))
    write(1, 'SCANA00001', '2026-11-15T01:00:00+00:00')
    write(2, 'SCANB00001', '2026-11-15T03:00:00+00:00')
    write(3, 'SCANA00001', '2026-11-15T02:00:00+00:00', status='running')
    write(4, 'SCANA00001', '2026-11-15T04:00:00+00:00', building=2)
    write(5, 'SCANA00001', '2026-11-15T05:00:00+00:00', space='9')
    runs = agent.list_runs(1, '', 'SCANA00001', directory=tmp_path)
    assert [r['id'][-1] for r in runs] == ['3', '1', '2']  # other buildings and spaces are left out
    assert runs[0]['status'] == 'interrupted'  # a run no process is working on is not shown as running
    assert agent.store_run({'mode': 'test'}) is False
