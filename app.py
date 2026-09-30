import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from services import ServiceError, find_meals, firestore, login, make_plan, recommend

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
        st.caption('⏱ ' + recipe['time'])
        if recipe.get('source_id'):
            st.caption('แปลหรือดัดแปลงโดย AI จาก ' + recipe.get('original_name', 'TheMealDB'))
            st.link_button('ดูสูตรต้นฉบับ · TheMealDB ↗', 'https://www.themealdb.com/meal/' + recipe['source_id'])
        else:
            st.caption('✨ สูตรที่ AI เสนอ • ไม่มีสูตรต้นฉบับใน TheMealDB')
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


with st.sidebar:
    st.markdown('## 🥗 Menu Mate')
    st.caption('มื้อที่ใช่ เริ่มจากสิ่งที่คุณมี')
    page = st.radio('เมนู', ['หาเมนูวันนี้', 'เมนูโปรด', 'ประวัติคำแนะนำ'], label_visibility='collapsed')
    st.divider()
    if st.session_state.user:
        st.caption('เข้าสู่ระบบแล้ว')
        st.write(st.session_state.user['email'])
        if st.button('ออกจากระบบ', use_container_width=True):
            for name, value in [('user', None), ('history', []), ('favorites', []), ('result', None)]:
                st.session_state[name] = value
            st.rerun()
    else:
        st.caption('เข้าสู่ระบบเพื่อค้นหาและเก็บเมนูของคุณ')
    st.caption('สูตรและรูปภาพ: TheMealDB • คำแนะนำภาษาไทย: Gemini')


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
                        st.session_state.user = user
                        st.session_state.history = []
                        st.session_state.favorites = []
                        st.session_state.result = None
                        st.rerun()
    st.caption('บัญชีจัดการด้วย Firebase Authentication และเก็บโปรไฟล์ใน Firestore')
    st.stop()

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
with st.form('preferences'):
    question = st.text_area('วัตถุดิบที่มี พร้อมปริมาณถ้าทราบ' if pantry else 'วันนี้อยากกินอะไร?',
                            placeholder='เช่น ไข่ 2 ฟอง หมูสับ ข้าวสวย ต้นหอม ซีอิ๊ว และน้ำมัน' if pantry else 'เช่น อยากกินเมนูเส้น มีอะไรแนะนำบ้าง',
                            height=110, max_chars=1500)
    a, b, c = st.columns(3)
    spice = a.selectbox('ความเผ็ด', ['ได้ทุกแบบ', 'ไม่เผ็ด', 'เผ็ดน้อย', 'เผ็ดมาก'])
    style = b.selectbox('ลักษณะอาหาร', ['ได้ทุกแบบ', 'แห้ง', 'น้ำ / ซุป'])
    diet = c.selectbox('รูปแบบการกิน', ['ทั่วไป', 'มังสวิรัติ (กินไข่และนม)', 'วีแกน', 'ไม่กินหมู'])
    a, b, c = st.columns(3)
    minutes = a.selectbox('เวลาทำอาหาร', [15, 30, 45, 60], index=1, format_func=lambda x: f'ไม่เกิน {x} นาที')
    budget = b.number_input('งบประมาณต่อมื้อ (บาท)', min_value=20, max_value=1000, value=100, step=10)
    servings = c.number_input('จำนวนคน', min_value=1, max_value=8, value=1)
    allergies = st.text_input('อาหารที่แพ้หรือวัตถุดิบที่ไม่กิน', placeholder='เช่น ถั่วลิสง กุ้ง นม หรือเว้นว่าง', max_chars=300)
    submitted = st.form_submit_button('หาเมนูที่ใช่ให้ฉัน  →', type='primary', use_container_width=True)

if not gemini:
    st.info('หน้าเว็บพร้อมแล้ว • เพิ่ม GEMINI_API_KEY ใน Secrets เพื่อเริ่มแนะนำเมนู ดูวิธีตั้งค่าใน README')
st.caption('คำแนะนำจาก AI อาจคลาดเคลื่อน ตรวจวัตถุดิบและฉลากเครื่องปรุงก่อนทำ โดยเฉพาะกรณีแพ้อาหาร')

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
        preferences = dict(mode='pantry' if pantry else 'craving', question=question.strip(), spice=spice,
                           style=style, diet=diet, minutes=minutes, budget_thb=budget, servings=servings, allergies=allergies)
        try:
            with st.status('กำลังหาไอเดียสำหรับมื้อนี้…', expanded=True) as status:
                st.write('ทำความเข้าใจความต้องการ')
                plan = make_plan(gemini, model, preferences)
                st.write('ค้นหาสูตรจาก TheMealDB')
                source_note = ''
                try:
                    sources = cached_meals(food_key, json.dumps(plan, sort_keys=True))
                    if not sources:
                        source_note = 'ไม่พบสูตรตรงกับคำค้นใน TheMealDB ครั้งนี้ใช้สูตรที่ AI เสนอ'
                except ServiceError:
                    sources = []
                    source_note = 'TheMealDB ไม่พร้อมใช้งาน ครั้งนี้ใช้สูตรที่ AI เสนอ'
                st.write('คัดเลือกและเรียบเรียงสูตรภาษาไทย')
                result = recommend(gemini, model, preferences, sources)
                result['source_note'] = source_note
                st.session_state.result = result
                status.update(label='จัดมื้อที่เหมาะกับคุณแล้ว', state='complete', expanded=False)
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
    st.download_button('ดาวน์โหลดคำแนะนำ', json.dumps(result, ensure_ascii=False, indent=2), 'menu-recommendations.json', 'application/json')
else:
    st.markdown('<div class="empty"><span>🥬 &nbsp; 🍜 &nbsp; 🥚</span><h3>มื้อดี ๆ เริ่มจากไอเดียเล็ก ๆ</h3><p>บอกสิ่งที่อยากกิน หรือวัตถุดิบที่มี แล้วให้เราช่วยคิดเมนู</p></div>', unsafe_allow_html=True)
