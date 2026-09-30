import hashlib

from streamlit_cookies_manager import EncryptedCookieManager


COOKIE_NAME = 'firebase_refresh'


def get_cookies(secret):
    password = hashlib.sha256(('menu-mate-session-v1:' + secret).encode()).hexdigest()
    return EncryptedCookieManager(prefix='menu-mate/', password=password)
