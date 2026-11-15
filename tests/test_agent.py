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
        dispatched = {}
        monkeypatch.setattr(agent, 'start_review', lambda building, space, scan: dispatched.update(
            building=building, space=space, scan=scan) or 'a' * 32)
        request = urllib.request.Request(base + '/api/spaces/1/reviews', data=b'{"space":"9","scan":"SAMPLE0001"}',
                                         headers={'Content-Type': 'application/json', 'Origin': base})
        with urllib.request.urlopen(request) as response:
            assert response.status == 202
            assert json.load(response) == {'id': 'a' * 32}
        assert dispatched == {'building': review.building, 'space': '9', 'scan': 'SAMPLE0001'}
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
