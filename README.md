# Menu Mate — วันนี้กินอะไรดี

เว็บภาษาไทยสำหรับงานกลุ่ม: Python + Streamlit + TheMealDB + Gemini + Firebase Firestore

## เริ่มในเครื่อง

เปิด Terminal ในโฟลเดอร์นี้ ใช้ Python 3.11 ขึ้นไป:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

ในเครื่อง: ใส่คีย์จริงใน `.env` ไฟล์เดียว แล้วบันทึกและรีสตาร์ต Streamlit หากดาวน์โหลดโค้ดจาก GitHub ให้สร้าง `.env` ตามตัวอย่างด้านล่าง
ไฟล์ `.env` ถูกกันไว้ใน `.gitignore` ห้ามอัปโหลดขึ้น GitHub

ตอน Deploy: ใส่ค่าใน Streamlit Secrets ตามรูปแบบ TOML ด้านล่าง ไม่ต้องอัปโหลด `.env`
ลำดับค่าที่ใช้: Streamlit Secrets ที่ไม่ว่าง → environment variables / `.env` → ค่าเริ่มต้น โดย `.env` ไม่ทับ environment variables ที่มีอยู่แล้ว

ใช้ค่าตัวอย่างนี้สำหรับ `.env` ในเครื่อง หรือวางในช่อง Secrets บนเว็บไซต์ Streamlit เมื่อ Deploy (ใช้รูปแบบนี้ได้ทั้งสองที่) ไม่ต้องสร้างไฟล์ `.example` หรือ `secrets.toml` เพิ่มในเครื่อง:

```toml
THEMEALDB_API_KEY = "1"
GEMINI_API_KEY = "คีย์ของคุณ"
GEMINI_MODEL = "gemini-2.5-flash-lite"
FIREBASE_API_KEY = "Web API Key จาก Firebase"
FIREBASE_PROJECT_ID = "Project ID จาก Firebase"
SESSION_COOKIE_PASSWORD = "ตั้งรหัสลับยาว ๆ สำหรับเข้ารหัสคุกกี้ (แนะนำ)"
```

ไม่ใช้ GOLDPRICE_API_KEY และไม่ใช้ OpenAI ในเวอร์ชันนี้ เปลี่ยน GEMINI_MODEL เป็นโมเดลที่บัญชีคุณรองรับได้
ถ้าไม่มีคีย์ หน้าเว็บยังเปิดหน้าสมัคร/เข้าสู่ระบบได้ แต่ต้องตั้งค่า Firebase ก่อนใช้งาน ระบบกำหนดให้เข้าสู่ระบบก่อนค้นหาเมนู

## ตั้งค่า Firebase ครั้งแรก

1. เปิด Firebase Console สร้าง/เลือกโปรเจกต์ Spark
2. Project settings → General: คัดลอก Project ID และ Web API Key (ลงทะเบียน Web app หากยังไม่มี)
3. Authentication → Sign-in method → เปิด Email/Password
4. Firestore Database → Create database → Standard edition และฐานข้อมูล `(default)` เลือก Production mode
5. เปิดแท็บ Rules วางเนื้อหาจาก `firestore.rules` ทั้งหมด แล้วกด Publish
6. ใส่ FIREBASE_API_KEY และ FIREBASE_PROJECT_ID ใน `.env` สำหรับเครื่อง หรือหน้า Secrets สำหรับ Deploy ให้เป็นโปรเจกต์เดียวกัน
7. เปิดเว็บ สมัครสมาชิกด้วยอีเมลและรหัสผ่านอย่างน้อย 6 ตัว แล้วลองเก็บเมนูโปรด

แอปใช้ Firebase Auth REST แลก ID token แล้วใช้ token ของผู้ใช้เรียก Firestore REST จึงไม่ต้องใช้ไฟล์ service account/private key
Rules อนุญาตเฉพาะเจ้าของอ่านและเขียน `users/{uid}/history`, `users/{uid}/favorites` และ `users/{uid}/profile/account`
ไม่เปิด `allow read, write: if true` ข้อมูลประวัติแสดงล่าสุด 30 รายการ ข้อมูลเก่ายังอยู่ในฐานข้อมูล
สมัครด้วยอีเมล รหัสผ่าน และยืนยันรหัสผ่าน บัญชีถูกจัดการใน Firebase Authentication รหัสผ่านไม่ถูกเขียนลง Firestore
Firestore เก็บโปรไฟล์ UID/อีเมล หลังเข้าสู่ระบบ หากบันทึกโปรไฟล์ไม่สำเร็จ แอปจะแจ้งและลองซิงก์ใหม่ในการทำงานรอบถัดไป บัญชี Auth ที่สร้างสำเร็จแล้วยังใช้เข้าสู่ระบบได้
ปุ่มออกจากระบบล้างบัญชี ประวัติ เมนูโปรดและผลลัพธ์ในเซสชัน แล้วกลับหน้าเข้าสู่ระบบ ข้อมูลใน Firebase ยังคงอยู่
การเข้าสู่ระบบจะคงอยู่เมื่อรีเฟรชเว็บในเบราว์เซอร์เดิมด้วยคุกกี้เข้ารหัสที่เก็บ Firebase refresh token; เมนู ⋮ มุมขวาบนใช้สำหรับออกจากระบบและลบคุกกี้ หากไม่ตั้ง `SESSION_COOKIE_PASSWORD` แอปจะใช้ `GEMINI_API_KEY` เป็นความลับสำหรับเข้ารหัสแทน ต้องมีอย่างใดอย่างหนึ่งเพื่อเปิดใช้การคงสถานะล็อกอิน
ถ้าเคยตั้งค่า Rules เวอร์ชันก่อน ต้อง Publish `firestore.rules` ฉบับใหม่เพื่ออนุญาตโปรไฟล์ด้วย

## Deploy บน Streamlit Community Cloud

1. สร้าง GitHub repository แล้วอัปโหลดไฟล์ในโฟลเดอร์นี้รวม `.streamlit/config.toml` แต่ไม่รวม `.env`, `.venv`, `__pycache__`, `.streamlit/secrets.toml`
2. เข้า https://share.streamlit.io/ เลือก Create app และ repository/branch
3. Main file path: `app.py` ถ้าอัปโหลดทั้งโฟลเดอร์ให้ใช้ `menu-ai-app/app.py`
4. Advanced settings → Secrets: วางค่า TOML ด้านบนพร้อมคีย์จริง เลือก Python 3.11 หรือใหม่กว่าที่รองรับ
5. Deploy แล้วเปิดลิงก์จากอีกเครื่องเพื่อทดสอบ
6. ถ้าแก้คีย์ภายหลัง ใช้ App settings → Secrets

## การทำงาน

- อยากกินอะไร: พิมพ์ความต้องการ เลือกเผ็ด/ไม่เผ็ด น้ำ/แห้ง รูปแบบอาหาร เวลา งบ จำนวนคน และอาหารที่แพ้
- มีอะไรในตู้เย็น: พิมพ์วัตถุดิบรวมเครื่องปรุง ระบบแสดงสูตรและของที่ต้องเตรียมเพิ่ม
- Gemini แปลงไทยเป็นคำค้นอังกฤษ → TheMealDB ค้นแบบ single ingredient/name → โหลดรายละเอียดสูงสุด 6 สูตร → Gemini เลือก/ดัดแปลงสูงสุด 3 สูตรเป็นไทย
- เมนูจากฐานข้อมูลแสดงแหล่งต้นฉบับ เมนูที่ AI สร้างแสดงป้ายแยกชัดเจน ไม่มีการสร้าง URL รูปจาก AI
- หาก TheMealDB ขัดข้อง/ไม่มีผล จะแจ้งก่อนแสดงสูตร AI ถ้า Gemini ขัดข้องจะแสดงข้อผิดพลาด
- เก็บเมนูโปรด ประวัติ และดาวน์โหลดคำแนะนำเป็น JSON
- Cache สูตร 1 ชั่วโมง เว้นการค้นแต่ละเซสชัน 15 วินาที (ไม่ใช่ global rate limit)

## ข้อจำกัดที่ใช้ประกอบรายงาน

TheMealDB key `1` ใช้ทดสอบ/เรียนรู้ สำหรับเผยแพร่เป็นบริการ production ผู้ให้บริการแนะนำ supporter key; ตรวจเงื่อนไขก่อนเปิดบริการวงกว้าง
V1 ฟรีค้นวัตถุดิบทีละอย่าง แอปจึงค้นวัตถุดิบหลักแล้วให้ AI ประเมินข้อจำกัดทั้งหมด ไม่มีการอ้างว่าใช้ premium multi-ingredient API
เมนูไทยในฐานข้อมูลมีจำกัด สูตรเพิ่มเติมจาก AI ไม่ใช่สูตรที่ผ่านการรับรอง เวลาและงบเป็นค่าประมาณ ไม่คำนวณโภชนาการทางการแพทย์
การกรองสารก่อภูมิแพ้เป็นคำแนะนำของ AI ไม่รับประกันความปลอดภัย ต้องตรวจสูตรและฉลากเอง
Gemini Free Tier มีโควตาและเงื่อนไขการใช้ข้อมูล อย่าใส่ข้อมูลส่วนบุคคลที่ไม่จำเป็นลงในช่องค้นหา
Firestore บันทึกคำถามและผลลัพธ์เมื่อเข้าสู่ระบบ ผู้ดูแลโปรเจกต์ Firebase เข้าถึงข้อมูลได้

## ตรวจงานก่อนนำเสนอ

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

ทดสอบจริงหลังใส่คีย์: ขอเมนูเส้นไม่เผ็ด, ใส่ไข่/หมูสับ/ข้าว, ใส่ข้อจำกัดแพ้ถั่ว, สมัครและเข้าสู่ระบบ, บันทึกเมนูโปรด, ออกจากระบบแล้วเข้าซ้ำ, ใช้บัญชีที่สองตรวจว่าไม่เห็นข้อมูลบัญชีแรก

## ไฟล์หลัก

- `app.py`: หน้าเว็บและควบคุมการทำงาน
- `services.py`: Gemini, TheMealDB, Firebase Auth/Firestore
- `style.css`: รูปแบบหน้าจอ
- `firestore.rules`: สิทธิ์ข้อมูลรายบุคคล
- `.env`: ใส่คีย์จริงสำหรับรันในเครื่อง ห้ามอัปโหลดขึ้น GitHub
- `.streamlit/config.toml`: ตั้งค่าสีและรูปแบบ Streamlit ไม่ใช่ไฟล์คีย์
- `tests/`: ทดสอบหน้าจอและข้อผิดพลาดด้วยข้อมูลจำลอง ไม่ใช้เครดิต API

เอกสาร: https://themealdb.com/docs_api_guide.php • https://ai.google.dev/gemini-api/docs/structured-output • https://firebase.google.com/docs/firestore/use-rest-api • https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
