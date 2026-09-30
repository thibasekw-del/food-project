import copy
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from services import ServiceError, recommend, restore_login, token_for
from services import generate

RECIPE = dict(name='ข้าวผัดไข่', reason='ใช้วัตถุดิบที่มี', source_id='', ingredients=['ข้าว 1 ถ้วย', 'ไข่ 1 ฟอง'],
              missing=['น้ำมัน'], steps=['ผัดไข่ให้สุก ใส่ข้าว ผัดให้ร้อนทั่ว'], time='ประมาณ 15 นาที', tags=['ไม่เผ็ด'])
RESULT = dict(message='ลองเมนูนี้ครับ', recipes=[RECIPE])
BUY_RESULT = dict(message='ลองเลือกซื้อเมนูเหล่านี้', recipes=[dict(
    name='ก๋วยเตี๋ยวน้ำใส', reason='เป็นเมนูเส้นไม่เผ็ด', source_id='', tags=['เส้น', 'น้ำ'],
    estimated_price='ประมาณ 50–70 บาท', where_to_buy='ร้านก๋วยเตี๋ยวทั่วไป', kind='buy')])


class MenuTests(unittest.TestCase):
    def setUp(self):
        class TestCookies(dict):
            def ready(self):
                return True

            def save(self):
                pass

        self.cookies = TestCookies()
        self.cookie_patch = patch('auth_session.get_cookies', return_value=self.cookies)
        self.cookie_patch.start()
        self.addCleanup(self.cookie_patch.stop)

    def app(self, key=''):
        # Keep a developer's local .env from changing isolated UI tests.
        os.environ['FIREBASE_API_KEY'] = ''
        os.environ['FIREBASE_PROJECT_ID'] = ''
        os.environ['GEMINI_API_KEY'] = ''
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=15)
        at.secrets['GEMINI_API_KEY'] = key
        at.secrets['SESSION_COOKIE_PASSWORD'] = 'test-cookie-secret'
        at.secrets['FIREBASE_API_KEY'] = ''
        at.secrets['FIREBASE_PROJECT_ID'] = ''
        at.session_state['user'] = {'uid': 'test-user', 'email': 'test@example.com', 'profile_synced': True}
        return at.run()

    def test_login_gate_and_logout(self):
        at = self.app()
        self.cookies['firebase_refresh'] = 'old-token'
        at.session_state['history'] = [{'private': 'data'}]
        next(b for b in at.button if b.label == 'ออกจากระบบ').click().run()
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state.user)
        self.assertEqual(at.session_state.history, [])
        self.assertNotIn('firebase_refresh', self.cookies)
        self.assertEqual(len(at.text_area), 0)
        self.assertEqual([t.label for t in at.tabs], ['เข้าสู่ระบบ', 'สมัครสมาชิก'])

    @patch('services.firestore', return_value={})
    @patch('services.login', return_value={'uid': 'new-user', 'email': 'new@example.com', 'refresh': 'refresh-token'})
    def test_register_profile_and_login(self, auth, database):
        at = self.app()
        at.session_state['user'] = None
        at.secrets['FIREBASE_API_KEY'] = 'test-key'
        at.secrets['FIREBASE_PROJECT_ID'] = 'test-project'
        at.run()
        at.text_input(key='email-True').input('new@example.com')
        at.text_input(key='password-True').input('password123')
        next(x for x in at.text_input if x.label == 'ยืนยันรหัสผ่าน').input('password123')
        next(b for b in at.button if b.label == 'สมัครสมาชิก').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state.user['uid'], 'new-user')
        self.assertEqual(self.cookies['firebase_refresh'], 'refresh-token')
        self.assertTrue(auth.call_args.args[3])
        payload = database.call_args.args[-1]
        self.assertEqual(payload, {'uid': 'new-user', 'email': 'new@example.com'})
        self.assertNotIn('password', payload)

    @patch('services.request')
    def test_restore_login_validates_firebase_account(self, request):
        request.side_effect = [
            {'id_token': 'id-token', 'refresh_token': 'rotated-token', 'expires_in': '3600'},
            {'users': [{'localId': 'account-1', 'email': 'person@example.com'}]},
        ]
        user = restore_login('api-key', 'old-token')
        self.assertEqual(user['uid'], 'account-1')
        self.assertEqual(user['refresh'], 'rotated-token')
        self.assertEqual(request.call_count, 2)

    def test_initial_and_missing_key(self):
        at = self.app()
        self.assertFalse(at.exception)
        at.text_area[0].input('อยากกินเส้น')
        next(b for b in at.button if b.label.startswith('หาเมนูที่ใช่')).click().run()
        self.assertFalse(at.exception)
        self.assertIn('GEMINI_API_KEY', at.error[0].value)

    def test_empty_request(self):
        at = self.app('fake')
        next(b for b in at.button if b.label.startswith('หาเมนูที่ใช่')).click().run()
        self.assertTrue(at.warning)
        self.assertFalse(at.exception)

    @patch('services.make_plan', return_value={'ingredients': ['egg'], 'searches': []})
    @patch('services.find_meals', return_value=[])
    @patch('services.recommend')
    def test_pantry_favorite_and_history(self, mock_recommend, *_):
        mock_recommend.return_value = copy.deepcopy(RESULT)
        at = self.app('fake')
        at.radio[0].set_value('🥕 มีอะไรในตู้เย็น').run()
        at.text_area[0].input('ไข่ ข้าว')
        next(b for b in at.button if b.label.startswith('หาเมนูที่ใช่')).click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state.history), 1)
        self.assertEqual(mock_recommend.call_args.args[2]['mode'], 'pantry')
        next(b for b in at.button if b.label == '♡ เก็บเมนูนี้').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state.favorites), 1)
        with patch('services.firestore', return_value=at.session_state.favorites):
            at.sidebar.radio[0].set_value('เมนูโปรด').run()
        self.assertFalse(at.exception)
        self.assertTrue(any(x.value == 'ข้าวผัดไข่' for x in at.subheader))

    @patch('services.make_plan', return_value={'ingredients': [], 'searches': ['noodle']})
    @patch('services.find_meals', return_value=[])
    @patch('services.recommend')
    def test_craving_shows_buy_suggestions_without_recipe(self, mock_recommend, *_):
        mock_recommend.return_value = copy.deepcopy(BUY_RESULT)
        at = self.app('fake')
        at.text_area[0].input('อยากกินเมนูเส้นไม่เผ็ด')
        next(b for b in at.button if b.label.startswith('หาเมนูที่ใช่')).click().run()
        self.assertFalse(at.exception)
        self.assertEqual(mock_recommend.call_args.args[2], {'mode': 'craving', 'question': 'อยากกินเมนูเส้นไม่เผ็ด'})
        self.assertFalse(any(x.label == 'วัตถุดิบและวิธีทำ' for x in at.expander))

    @patch('services.generate', return_value=BUY_RESULT)
    def test_craving_uses_buy_schema(self, generate):
        result = recommend('fake', 'model', {'mode': 'craving', 'question': 'เส้น'}, [])
        self.assertEqual(result['recipes'][0]['kind'], 'buy')
        self.assertNotIn('steps', result['recipes'][0])
        self.assertIn('estimated_price', generate.call_args.args[-1]['properties']['recipes']['items']['properties'])
        self.assertNotIn('steps', generate.call_args.args[-1]['properties']['recipes']['items']['properties'])

    @patch('services.make_plan', side_effect=ServiceError('โควตาบริการเต็ม'))
    def test_ai_failure_is_visible(self, _):
        at = self.app('fake')
        at.text_area[0].input('เส้น')
        next(b for b in at.button if b.label.startswith('หาเมนูที่ใช่')).click().run()
        self.assertFalse(at.exception)
        self.assertIn('โควตา', at.error[0].value)

    @patch('services.generate')
    def test_hallucinated_source_is_removed(self, generate):
        result = copy.deepcopy(RESULT)
        result['recipes'][0]['source_id'] = 'invented'
        generate.return_value = result
        actual = recommend('fake', 'model', {}, [])
        self.assertEqual(actual['recipes'][0]['source_id'], '')
        self.assertEqual(actual['recipes'][0]['image'], '')

    @patch('services.generate', return_value={'message': 'ok', 'recipes': [{'name': 'incomplete'}]})
    def test_invalid_recipe_rejected(self, _):
        with self.assertRaises(ServiceError):
            recommend('fake', 'model', {}, [])

    @patch('services.time.sleep')
    @patch('services.request')
    def test_gemini_fallback_after_temporary_failures(self, request, _):
        request.side_effect = [ServiceError('บริการ AI ไม่พร้อมชั่วคราว')] * 3 + [
            {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"message":"ok"}'}]}}]}]
        result = generate('fake', 'gemini-3.6-flash', 'instruction', {}, {'type': 'OBJECT'})
        self.assertEqual(result['message'], 'ok')
        self.assertIn('gemini-3.5-flash-lite', request.call_args.args[1])
        self.assertEqual(request.call_count, 4)

    @patch('services.request')
    def test_gemini_fallback_when_primary_quota_is_full(self, request):
        request.side_effect = [ServiceError('โควตาบริการเต็มชั่วคราว'),
                               {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"message":"ok"}'}]}}]}]
        result = generate('fake', 'gemini-3.6-flash', 'instruction', {}, {'type': 'OBJECT'})
        self.assertEqual(result['message'], 'ok')
        self.assertEqual(request.call_count, 2)
        self.assertIn('gemini-3.5-flash-lite', request.call_args.args[1])

    @patch('services.request', return_value={'id_token': 'new', 'refresh_token': 'newrefresh', 'expires_in': '3600'})
    def test_expired_auth_refreshes(self, request):
        user = dict(expires=0, refresh='old', token='expired')
        self.assertEqual(token_for('fake', user), 'new')
        self.assertEqual(user['refresh'], 'newrefresh')


if __name__ == '__main__':
    unittest.main()
