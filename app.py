import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from auth_session import COOKIE_NAME, get_cookies
from services import ServiceError, find_meals, firestore, login, make_plan, recommend, restore_login, token_for

load_dotenv(Path(__file__).with_name('.env'), override=False)

st.set_page_config(page_title='วันนี้กินอะไรดี · Menu Mate', page_icon='🥗', layout='wide')
st.markdown('<style>' + Path(__file__).with_name('style.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)


def setting(name, default=''):
    try:
        return str(st.secrets.get(name) or os.getenv(name) or default)
    except FileNotFoundError:
        return os.getenv(name, default)


gemini = setting('GEMINI_API_KEY')
model = setting('GEMINI_MODEL', 'gemini-2.5-flash-lite')
food_key = setting('THEMEALDB_API_KEY', '1')
firebase_key = setting('FIREBASE_API_KEY')
project = setting('FIREBASE_PROJECT_ID')
firebase_ready = bool(firebase_key and project)
for name, default in [('user', None), ('history', []), ('favorites', []), ('result', None), ('last_request', 0)]:
    if name not in st.session_state:
        st.session_state[name] = default

cookie_secret = setting('SESSION_COOKIE_PASSWORD') or gemini
cookies = get_cookies(cookie_secret) if cookie_secret else None
if cookies is not None and not cookies.ready():
    st.stop()
if cookies is not None and firebase_ready:
    if not st.session_state.user and cookies.get(COOKIE_NAME):
        try:
            st.session_state.user = restore_login(firebase_key, cookies[COOKIE_NAME])
        except (ServiceError, KeyError, ValueError):
            del cookies[COOKIE_NAME]
            cookies.save()
    if st.session_state.user and 'expires' in st.session_state.user:
        try:
            token_for(firebase_key, st.session_state.user)
            if cookies.get(COOKIE_NAME) != st.session_state.user.get('refresh'):
                cookies[COOKIE_NAME] = st.session_state.user['refresh']
                cookies.save()
        except ServiceError:
            st.session_state.user = None
            if cookies.get(COOKIE_NAME):
                del cookies[COOKIE_NAME]
                cookies.save()


@st.cache_data(ttl=3600, show_spinner=False)
def cached_meals(key, plan_json):
    return find_meals(key, json.loads(plan_json))


def save(collection, payload, doc_id):
    user = st.session_state.user
    if user and firebase_ready:
        firestore(project, firebase_key, user, collection, doc_id, payload)
    st.session_state[collection] = [payload] + [x for x in st.session_state[collection] if x.get('id') != payload['id']]
    st.session_state[collection] = st.session_state[collection][:30]


def recipe_card(recipe, key):
    with st.container(border=True):
        if recipe.get('image', '').startswith('https://www.themealdb.com/'):
            st.image(recipe['image'], use_container_width=True)
        else:
            st.markdown('<div class="food-placeholder">🍲</div>', unsafe_allow_html=True)
        st.subheader(recipe['name'])
        st.caption(' · '.join(recipe.get('tags', [])))
        st.write(recipe['reason'])
        buying = recipe.get('kind') == 'buy'
        if buying:
            st.caption('💸 ' + recipe['estimated_price'] + ' (ราคาโดยประมาณ)')
            st.write('📍 ' + recipe['where_to_buy'])
        else:
            st.caption('⏱ ' + recipe['time'])
        if recipe.get('source_id'):
            st.caption('ภาพและข้อมูลเมนูอ้างอิงจาก TheMealDB: ' + recipe.get('original_name', ''))
            if not buying:
                st.link_button('ดูสูตรต้นฉบับ · TheMealDB ↗', 'https://www.themealdb.com/meal/' + recipe['source_id'])
        else:
            st.caption('✨ เมนูที่ AI เสนอ • ไม่มีภาพอ้างอิงจาก TheMealDB')
        if not buying:
            with st.expander('วัตถุดิบและวิธีทำ'):
                st.markdown('**วัตถุดิบ**')
                for item in recipe['ingredients']:
                    st.write('• ' + item)
                if recipe['missing']:
                    st.markdown('**ต้องเตรียมเพิ่ม**')
                    st.write(' · '.join(recipe['missing']))
                st.markdown('**ลงมือทำ**')
                for i, step in enumerate(recipe['steps'], 1):
                    st.write(f'{i}. {step}')
        if st.button('♡ เก็บเมนูนี้', key=key, use_container_width=True):
            item = dict(recipe)
            item['id'] = hashlib.sha256(json.dumps(recipe, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
            try:
                save('favorites', item, item['id'])
                st.toast('บันทึกเมนูโปรดแล้ว')
            except ServiceError as exc:
                st.error(str(exc))


if st.session_state.user:
    _, menu_column = st.columns([12, 1])
    with menu_column:
        with st.popover('⋮', help='เมนูบัญชี'):
            st.caption(st.session_state.user['email'])
            if st.button('ออกจากระบบ', use_container_width=True):
                if cookies is not None and cookies.get(COOKIE_NAME):
                    del cookies[COOKIE_NAME]
                    cookies.save()
                for name, value in [('user', None), ('history', []), ('favorites', []), ('result', None)]:
                    st.session_state[name] = value
                st.rerun()


st.markdown('<div class="eyebrow">YOUR EVERYDAY KITCHEN COMPANION</div>', unsafe_allow_html=True)
st.title('วันนี้กินอะไรดี?')
st.markdown('เปลี่ยนความอยากและของในตู้เย็น ให้เป็นมื้ออร่อยที่เหมาะกับคุณ')

if not st.session_state.user:
    st.subheader('ยินดีต้อนรับสู่ครัวของคุณ')
    if not firebase_ready:
        st.info('กรุณาตั้งค่า FIREBASE_API_KEY และ FIREBASE_PROJECT_ID ใน Secrets เพื่อเปิดใช้ระบบสมาชิก')
    signin_tab, signup_tab = st.tabs(['เข้าสู่ระบบ', 'สมัครสมาชิก'])
    for tab, signup in [(signin_tab, False), (signup_tab, True)]:
        with tab:
            with st.form('register' if signup else 'signin', clear_on_submit=True):
                email = st.text_input('อีเมล', max_chars=200, key=f'email-{signup}')
                password = st.text_input('รหัสผ่าน (อย่างน้อย 6 ตัว)', type='password', max_chars=128, key=f'password-{signup}')
                confirm = st.text_input('ยืนยันรหัสผ่าน', type='password', max_chars=128) if signup else password
                submit_auth = st.form_submit_button('สมัครสมาชิก' if signup else 'เข้าสู่ระบบ', type='primary', disabled=not firebase_ready)
            if submit_auth:
                if '@' not in email or len(password) < 6:
                    st.error('กรุณาระบุอีเมลและรหัสผ่านอย่างน้อย 6 ตัว')
                elif password != confirm:
                    st.error('รหัสผ่านทั้งสองช่องไม่ตรงกัน')
                else:
                    try:
                        user = login(firebase_key, email.strip(), password, signup)
                    except ServiceError:
                        st.error('ดำเนินการไม่สำเร็จ ตรวจอีเมล/รหัสผ่าน หากเคยสมัครแล้วให้ใช้หน้าเข้าสู่ระบบ')
                    else:
                        if cookies is not None and user.get('refresh'):
                            cookies[COOKIE_NAME] = user['refresh']
                            cookies.save()
                        st.session_state.user = user
                        st.session_state.history = []
                        st.session_state.favorites = []
                        st.session_state.result = None
                        st.rerun()
    st.caption('บัญชีจัดการด้วย Firebase Authentication และเก็บโปรไฟล์ใน Firestore')
    st.stop()

page = st.radio('หน้าเว็บ', ['หาเมนูวันนี้', 'เมนูโปรด', 'ประวัติคำแนะนำ'], horizontal=True)

# Retry profile sync on subsequent runs if Firestore was not configured at signup.
if not st.session_state.user.get('profile_synced'):
    user = st.session_state.user
    try:
        firestore(project, firebase_key, user, 'profile', 'account', {'uid': user['uid'], 'email': user['email']})
        user['profile_synced'] = True
    except ServiceError:
        st.warning('บัญชีอยู่ใน Firebase Authentication แล้ว แต่ยังบันทึกโปรไฟล์ไม่ได้ กรุณาตรวจ Firestore Rules แล้วรีเฟรช')

if page != 'หาเมนูวันนี้':
    collection = 'favorites' if page == 'เมนูโปรด' else 'history'
    st.header('♡ เมนูโปรด' if collection == 'favorites' else '↺ ประวัติคำแนะนำ')
    if st.session_state.user:
        try:
            st.session_state[collection] = firestore(project, firebase_key, st.session_state.user, collection)
        except ServiceError as exc:
            st.error(str(exc))
    items = st.session_state[collection]
    if not items:
        st.info('ยังไม่มีรายการ ลองหาเมนูแรกของคุณได้เลย')
    elif collection == 'favorites':
        columns = st.columns(3)
        for i, item in enumerate(items):
            with columns[i % 3]:
                recipe_card(item, f'fav-{i}')
    else:
        for i, item in enumerate(items):
            with st.expander(item['question']):
                st.caption(item.get('created', ''))
                st.write(item['result']['message'])
                for j, recipe in enumerate(item['result']['recipes']):
                    recipe_card(recipe, f'history-{i}-{j}')
    st.stop()

st.markdown('<div class="intro">01 &nbsp; บอกเราเกี่ยวกับมื้อของคุณ</div>', unsafe_allow_html=True)
mode = st.radio('เลือกวิธีค้นหา', ['💭 อยากกินอะไร', '🥕 มีอะไรในตู้เย็น'], horizontal=True)
pantry = mode.startswith('🥕')
if st.session_state.get('last_mode') != mode:
    st.session_state.result = None
    st.session_state.last_mode = mode
with st.form('preferences'):
    question = st.text_area('วัตถุดิบที่มี พร้อมปริมาณถ้าทราบ' if pantry else 'วันนี้อยากกินอะไร?',
                            placeholder='เช่น มีไข่กับข้าว ทำอะไรได้บ้าง' if pantry else 'เช่น อยากกินเส้นไม่เผ็ด งบไม่เกิน 80 บาท',
                            height=110, max_chars=1500)
    submitted = st.form_submit_button('หาเมนูที่ใช่ให้ฉัน  →', type='primary', use_container_width=True)

if not gemini:
    st.info('หน้าเว็บพร้อมแล้ว • เพิ่ม GEMINI_API_KEY ใน Secrets เพื่อเริ่มแนะนำเมนู ดูวิธีตั้งค่าใน README')
st.caption('คำแนะนำจาก AI อาจคลาดเคลื่อน ราคาและเวลาที่ระบุเป็นเพียงการประมาณ ตรวจวัตถุดิบและข้อมูลสารก่อภูมิแพ้ก่อนกินหรือทำอาหาร')

if submitted:
    if not question.strip():
        st.warning('กรุณาบอกความต้องการหรือวัตถุดิบก่อนครับ')
    elif not gemini:
        st.error('ยังไม่ได้ตั้งค่า GEMINI_API_KEY')
    elif time.time() - st.session_state.last_request < 15:
        st.warning('กรุณารอสักครู่ก่อนค้นหาอีกครั้ง')
    else:
        st.session_state.last_request = time.time()
        st.session_state.result = None
        preferences = dict(mode='pantry' if pantry else 'craving', question=question.strip())
        try:
            with st.spinner('กำลังหาเมนูให้คุณ…'):
                plan = make_plan(gemini, model, preferences)
                source_note = ''
                try:
                    sources = cached_meals(food_key, json.dumps(plan, sort_keys=True))
                    if not sources:
                        source_note = 'ไม่พบเมนูตรงกับคำค้นใน TheMealDB ครั้งนี้ใช้เมนูที่ AI เสนอ'
                except ServiceError:
                    sources = []
                    source_note = 'TheMealDB ไม่พร้อมใช้งาน ครั้งนี้ใช้เมนูที่ AI เสนอ'
                result = recommend(gemini, model, preferences, sources)
                result['source_note'] = source_note
                st.session_state.result = result
            entry = {'id': uuid.uuid4().hex, 'question': question.strip(), 'created': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()), 'result': result}
            try:
                save('history', entry, entry['id'])
            except ServiceError:
                st.session_state.history.insert(0, entry)
                st.warning('ได้คำแนะนำแล้ว แต่บันทึก Firebase ไม่สำเร็จ ประวัตินี้เก็บเฉพาะเซสชัน')
        except ServiceError as exc:
            st.error(str(exc))

if st.session_state.result:
    result = st.session_state.result
    st.markdown('<div class="intro">02 &nbsp; มื้อนี้ เลือกได้เลย</div>', unsafe_allow_html=True)
    st.write(result['message'])
    if result.get('source_note'):
        st.info(result['source_note'])
    columns = st.columns(3)
    for i, recipe in enumerate(result['recipes']):
        with columns[i]:
            recipe_card(recipe, f'result-{i}')
else:
    st.markdown('<div class="empty"><span>🥬 &nbsp; 🍜 &nbsp; 🥚</span><h3>มื้อดี ๆ เริ่มจากไอเดียเล็ก ๆ</h3><p>บอกสิ่งที่อยากกิน หรือวัตถุดิบที่มี แล้วให้เราช่วยคิดเมนู</p></div>', unsafe_allow_html=True)
