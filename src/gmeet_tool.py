import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
import os
from selenium_stealth import stealth

# --- PASTE YOUR COOKIE DATA HERE ---
# For testing, you can paste the content of your cookies.json file here
# as a multi-line string.
HARDCODED_COOKIES = """
[
    {
        "domain": ".google.com",
        "expirationDate": 1785170597.676983,
        "hostOnly": false,
        "httpOnly": false,
        "name": "SAPISID",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "ln2jr2klyWN7Cf_4/Ab_m-U-RZaTodNr8w"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1785170597.677106,
        "hostOnly": false,
        "httpOnly": false,
        "name": "__Secure-3PAPISID",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "ln2jr2klyWN7Cf_4/Ab_m-U-RZaTodNr8w"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1761415146.763028,
        "hostOnly": false,
        "httpOnly": true,
        "name": "AEC",
        "path": "/",
        "sameSite": "lax",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "AVh_V2jXrr4k3ADqrVpAXM6AndTkx7wcIYqe5NOZI8B21wfvm0m08d6bDw"
    },
    {
        "domain": "accounts.google.com",
        "expirationDate": 1751515887,
        "hostOnly": true,
        "httpOnly": false,
        "name": "OTZ",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "8110331_34_34__34_"
    },
    {
        "domain": "accounts.google.com",
        "expirationDate": 1785170529.12672,
        "hostOnly": true,
        "httpOnly": true,
        "name": "ACCOUNT_CHOOSER",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "AFx_qI7AUvZrm29SDhdKZlHvSb9E5g4B2lO-1iuXpbyMRW8qkWVMVPQcG56f0lcP15bUghp5v8VMlA-CEZXBx04qZ-VTG9AEcMbzNheeLtG_gzoXz65JsDQu9PzzMS3Ec_r9_djywb4-QvEI-Bh0nanDnAtB_h9B43y3E520NN2YXvqwW9e7NfakGeTwlsSGnlq_s1tH5cZASxvEFrr9KNCZ6aeLpDPctQsU4hnZJeSrsW8mrJfs8SDJMPa6xmNKHMMY_Bn9rwN-hzLYttLnalzBCrhSHQGXwC4jya0L8xCwiJQ91TvCZXLFoFA0zoqTyHim_n1iwr1F9W2lnUYGTvRax4l56SN9TIcS9ZkcsyjgS2-3q4fm2YUftxpZi7S8NjrXWJed5SN-63WpBc3GcRDx6Zps0WrWTdR3U9xPVTsDaE7XsXpZGka8K9jpbMUa34MgxiEel72kO8htbNYQ8-sW5nw0VHO1zfatni2O_697gnNs0vN2K9-fcnA0XyZyuOYYwGJt61xS_cCxZH75wRtMq7HVdtoPu8f80CnrXWTCOcbry_c7wbGXwh1eL4FvEAPVR84Fnix-"
    },
    {
        "domain": "accounts.google.com",
        "expirationDate": 1781954544.991397,
        "hostOnly": true,
        "httpOnly": false,
        "name": "LSOLH",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "_SVI_ENro25zx_40DGBAiP01BRURIZl9xQTJkdmozdlAyaWF1NFlSOUlWMllCclcwNDZ5MjJfOUFDeVk5MkRGQlQ5bnJ0VHVybGtaZXY4QQ_:29173657:590b"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1766412451.675845,
        "hostOnly": false,
        "httpOnly": true,
        "name": "NID",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "524=XY0M5v-axzPP06Pk5iLFE-gZqBnP_0czY5mlMn_CvNk7TcHeeE7CkFSPDhZBkZHbKLuM8xhOsZMWhqjUPyShxxGz3CKNgpG1vmMH_3Ls3L6AdOd1jN5tf7W3XtVFUGVCBzsA7ZgP7-m5VUHwIAyPGMOj74Ub43hdWrqlFchxhFjb2JX86fg2i_tObqlOgV-jLwy0rTSP7r0ork9D0-Ki638G5WBJpgBBm9tIdRcqZ9zOeYjVYRDuTu5BqsjXyFoa9Bzq5Jh02tEGL8SuJTKq-S3lgZ1fPAKS4cpeQ-S3OXgbgBRQ51qy06IFGnqV8BvWP-e74NEzV23uAds7bx-0cZzQhP6WUenQKeCNPxde1dUCMpZyBWATo2JGbzkEQH78x5igPcztJuKjtmDf43wvGOdPTxl9Mja_Jxp5Ba_uvEMBVHkxV4r_zzdny_CtdJ9tEjuH9N8SmEFysa_KpE7qTv23VAYXQtqg8FZlJpzDnnOuVspcJWuEMpUprY_Tda9eeRXjCWk7Ln-k58Le7gAewPjW0Gln2CQaDauPIyMoPcXDdaL-w1Tfd1uXnChpYtBGGic7CHBpQCTiEUhAJgZxc6JHU2pct6XuqZS0HR8CwK0CGGCiMjgeyRTAMdZgkgAosGVx8oumfRgYsVR7OdmlvQk2stwJPlU6v-VuWdgb_4A8fyJw4BSxToQ770qUarbGFQ_pYMA5AoLrdzgtbr0v_34bGl6UrfCXvDq-ayzg6TZGm27gTVv_CDo-sqXv-PN4cyI_H7MOGB83K_0KpOCumtjVqZrEo6HL_3mezTvuCz-Cqw--TJtgiooWSbhZq3f3gtQOhlRksFE7GYyUheaAKvC31rMmXK5tIDRrYsm-ko0vQneJ3SQU2MKXqnAxCVdJi3ZaNzf6CUep74nMafv33lZZ1klblr7Kf3hVPfRJ6ccU2Z1SUvwdUbF6ixLWqCelKa9k7NnJgFHn8XAeehYabKhz2_Dgv8DcnUpSClgwJsVGvQ5sxuyO7dklUTVKo18UTcXSmeI2h19WSHX_8X4vkd5HwnzRSzJD0bRzPwxT_w_rh_owxMYJFIvkjEOTUED8eaZQoqUtDHPO3bIpxKlfS5-vsbKHiS9O_d5lQLm4fiGXTuTqcmtffIaR2NxoEaDtGPN3YpW7YFDSOBlN3BfG9EeAX4wu-3J0t9d_JOooywEvuNbpnMq2jEg1BIPgpAmbgJxkk-6zjAq79jS5j8UjRR0JxhmgKs3rXpDDxz3dD9vR8Hx5yEcjjhRlE435gyGxvqkauiBnWrh1Vqfp65Qo_e2pNHwHUouPSwxVILbRjlxtqrgKDgSCKuHFal7kSOW648giCYa4z8pFWNjYataya3gTkjEJ3vWp_Qsim-JG4NL0rJ6gM8-vtVnWAeSy18Ei9xbWaPDD1vtyyKsLwtA40QYKymwa7WsQV7i8LVhF9vQ3S-QgkhXe2aACz3Sv_36-lREOx9T2eDU30sgnNfwGiNQX8Y2PmRUKFzmX9d1Lg8kPmuKn_XH1pb5j4zgOMN9RfYun_-Tp6KPk6IIFRgW3F27fQkhgXYyF-LcGL8Au18T8OH8I1g4bfCnnBW_9uPxH7QgMQdc0SrV9tJxptX2zaJiGvRJfnOBmJIbWyLjW5Y0DgBGDS1NPMySoge6xJOrMlHi-eusuxnn4wIhMokDmew_rCuWBhu94lPrjwk_j205SFPvbke_VCWNRj2JECNFK5znEpNJcax933pVgCliFCSNQeq2p5XmXBG4q86RHInq4P1_7QX6aTI4eBO8zN1zLuZhjDJy6EHvJ0Wn3KJmQFoiPRIyBipwAziWj7jZAQkmzE5NZ1CVK_7plAURoOc6dlT5wqEiGg_VHykXZEjFcaix64iRumJ_X3iaB0liLw0P_xw_js3E5j-F1E1JUIovf_e7zbBmaX9NoinSphvRZs6N-Dc1Gkjh4-RbrDlG6rN7AWb0XUIOXnM9O53etlq-uGH8ozAbx0vaoXFQGRK1e245Mccj3wdw8BtpSRqztY29yOeEbvhyCP7EhBxYkD6WDKq3Uh-QRLzp-6Q8_LsiRAe3rXD8kl8da7FS41EeuRpmBeVUZ_0eddBu9dRedFFFCHM0TXKtMzxYoTt5iVuDmkyttwybrR2e5ddgQweWfCtHsCmv9L2mWxsb-UT_Lc1BDurz2H-ndeSdJVd_uq-fOGCTnEAoicnpgm-FVuQAAL9GaYLT1okOe8yxR4MQZ1DonnKA9u3I3toUAmZWDB6ADq91V7VXP3xC50WHEt8Lb91sMOMY6B51IP48hBpoe_4QSI1S5ZN4Q9Rqr4D-nPWFKGXgobPz4bMOwWTaWE7pSxZrZwi5Ge5WEspCCTBeb4S_AawRdWP0FLm1XRUB0sLT4ALC6Yvf2BU-JlRaR3hwPEuEACs6Fr9JrAEGR7VjwzJzYsc3xzmorv9daudpdIOtJQoeYP5BC7kAdbgkdmDckXmIlnqYH3GZFBXeUmXHoXX9W1MZkF-KP1uJ__BA_sWj-AcU_P-fPbJCaJO_kdeua9qPfAytPzskAZPyJ2npDRzqzBOLMzRHW6h9UZRNVc5YjVmyQJp-GtGsSV86YhvRi93vQ6Glhvt46wmy7v5_NeT_5NrZ9pWFV1ohKAlPjXp2vbCtjy4FAYFfpn9_ICKWxr42vui1tpjTRkzUBxjoVnAQZL44uLEr7fEeC4DE5FdwAIaQ8JaPDf_9wfiSmzhNxrI4Ku2e8ybwOsK4Qqe0rkcY"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1782146252.552774,
        "hostOnly": false,
        "httpOnly": true,
        "name": "__Secure-1PSIDTS",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "sidts-CjIB5H03P05cBChF_64lqvPYwIOwn5rNZ7F40BYJIa67IL7MTMzb0BRr9rpFrgBjDwiREhAA"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1785170597.677045,
        "hostOnly": false,
        "httpOnly": false,
        "name": "__Secure-1PAPISID",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "ln2jr2klyWN7Cf_4/Ab_m-U-RZaTodNr8w"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1785170597.676488,
        "hostOnly": false,
        "httpOnly": true,
        "name": "__Secure-3PSID",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "g.a000yQgoJvzO1BjM6palIhIj3zKrCxp86crP0naMAaWcDn2zZxq-204DGbtP297eisZ7CmB5tQACgYKAc4SARESFQHGX2MiR361hFWTSUpNzjf9AT5mzBoVAUF8yKquBWuZUhrZBJXVFTJ2qgek0076"
    },
    {
        "domain": "accounts.google.com",
        "expirationDate": 1785170597.676708,
        "hostOnly": true,
        "httpOnly": true,
        "name": "__Host-1PLSID",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "o.calendar.google.com|o.chat.google.com|o.chromewebstore.google.com|o.console.cloud.google.com|o.drive.fife.usercontent.google.com|o.drive.google.com|o.gds.google.com|o.groups.google.com|o.lens.google.com|o.mail.google.com|o.meet.google.com|o.myaccount.google.com|o.photos.fife.usercontent.google.com|o.photos.google.com|o.play.google.com|o.script.google.com|s.IN|s.TW|s.youtube:g.a000yQgoJs_Kx86nuLOXsmniSibv1aiAJdPKN0vwuP2O3IYUItofzYZ58jEADqvyU5GMx_cHAwACgYKAQQSARESFQHGX2MirtpumHWurvD4BXcmRQHCxhoVAUF8yKqvAAOrtCvUb1wmuuSB07Mi0076"
    },
    {
        "domain": "accounts.google.com",
        "expirationDate": 1785170597.676755,
        "hostOnly": true,
        "httpOnly": true,
        "name": "__Host-3PLSID",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "o.calendar.google.com|o.chat.google.com|o.chromewebstore.google.com|o.console.cloud.google.com|o.drive.fife.usercontent.google.com|o.drive.google.com|o.gds.google.com|o.groups.google.com|o.lens.google.com|o.mail.google.com|o.meet.google.com|o.myaccount.google.com|o.photos.fife.usercontent.google.com|o.photos.google.com|o.play.google.com|o.script.google.com|s.IN|s.TW|s.youtube:g.a000yQgoJs_Kx86nuLOXsmniSibv1aiAJdPKN0vwuP2O3IYUItofJwkLnp5PMbgMvfCODJeWYQACgYKAUsSARESFQHGX2Mi5N7ql8mjm4wrIrUH5X86VBoVAUF8yKpzENNZm4na-mCuiETRaA5Q0076"
    },
    {
        "domain": "accounts.google.com",
        "expirationDate": 1785170597.67717,
        "hostOnly": true,
        "httpOnly": true,
        "name": "__Host-GAPS",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "1:gyDMo_Im8E55Amyw7NDYASSdYLura-8UanHBboz8oSP4BPUG2MttPaeTQd-WSf8k5t5s4LM50S-83EXOV2cUmaQj21i__OD6-zgmsWvKZAbaNl_OZ2xNyVTXG5GF9ZAcqtkvHNxPWY4HthOkSBw4OB5OJ-fPJuWaNKYJN69_lMhVCR_nNopA52yf2zIT-w:_a6G99trwFmODvKX"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1785170597.676352,
        "hostOnly": false,
        "httpOnly": true,
        "name": "__Secure-1PSID",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "g.a000yQgoJvzO1BjM6palIhIj3zKrCxp86crP0naMAaWcDn2zZxq-iYtu7E2YnFemU9ThZ8PWaQACgYKAWgSARESFQHGX2MinM25e5ZcdPsQWZsPaTn4vRoVAUF8yKqsF74GUisLkN4HaP4qchd60076"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1782146636.118948,
        "hostOnly": false,
        "httpOnly": true,
        "name": "__Secure-1PSIDCC",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "AKEyXzVHmF7KiktLsHyKzfGKT7q8PKas8jCaXt-rIezbhs3xPKf-DKy7f8vuE5PX0y0gSW9tIO5Z"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1782146636.11902,
        "hostOnly": false,
        "httpOnly": true,
        "name": "__Secure-3PSIDCC",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "AKEyXzXONAJlanG_cY5T17nRdVRZzj7bKA7CurLi_9Vt85T1l4Xctd6Ia59U51xLoi9WJfK8A5S9"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1782146252.553034,
        "hostOnly": false,
        "httpOnly": true,
        "name": "__Secure-3PSIDTS",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "sidts-CjIB5H03P05cBChF_64lqvPYwIOwn5rNZ7F40BYJIa67IL7MTMzb0BRr9rpFrgBjDwiREhAA"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1759499120.023553,
        "hostOnly": false,
        "httpOnly": true,
        "name": "__Secure-ENID",
        "path": "/",
        "sameSite": "lax",
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "23.SE=kDlZcOS-0rpEEk3MW0bay2a-DZMpCWiMpuCswJjWzfg6N3Y1qkPmKDtvpPEcc8IB6SIM3HnmjHrhf09seXn0BTdNSZ7gmspdoz_v6BbeiAjtu4T8MBlMOJo-vyCQr3r3vRRIiczf8JuOG9QPMQFDyTSLOfIzSqOQSswd-9slGD2UTTdM7pchda_9mz-kLg5Mjp7sCMdoxdfIKvSFos7yy4bvssmBM0aNlS_oLdIdDtQ6IVpTuwzQVnQ1MsCLjvbbC_d1iU8eU8ur7rbl2JQSyQNzBb4iQ5AMhJeeXdiyMcfcjTM4gqsMIdYpIg_x59g-CNMW5yDg2RVO31dAS1bf21Bxc8BEtlX2W8DMuooau8xgJrfs8vfd9h1vYH9w6ShWNAJ5kDYuxs0jV5Vfgl2-5vDHrrKLcf1H"
    },
    {
        "domain": "accounts.google.com",
        "expirationDate": 1785170597.676611,
        "hostOnly": true,
        "httpOnly": true,
        "name": "LSID",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "o.calendar.google.com|o.chat.google.com|o.chromewebstore.google.com|o.console.cloud.google.com|o.drive.fife.usercontent.google.com|o.drive.google.com|o.gds.google.com|o.groups.google.com|o.lens.google.com|o.mail.google.com|o.meet.google.com|o.myaccount.google.com|o.photos.fife.usercontent.google.com|o.photos.google.com|o.play.google.com|o.script.google.com|s.IN|s.TW|s.youtube:g.a000yQgoJs_Kx86nuLOXsmniSibv1aiAJdPKN0vwuP2O3IYUItofJ0UHbMIOwTi5KY_TfGIcgQACgYKAX4SARESFQHGX2MiaGF7ZKuDgHY3VxLtMvTYMBoVAUF8yKoBeiMcDSJQyNN3AqulmyKy0076"
    },
    {
        "domain": ".google.com",
        "expirationDate": 1785170597.676861,
        "hostOnly": false,
        "httpOnly": true,
        "name": "SSID",
        "path": "/",
        "sameSite": null,
        "secure": true,
        "session": false,
        "storeId": null,
        "value": "ABWSIZRblibTtTx0L"
    }
]
"""
# ------------------------------------

def join_gmeet(meet_url: str):
    """
    Joins a Google Meet by loading hardcoded cookies.
    """
    print("\n--- [G-Meet Job Started] ---")
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_experimental_option("detach", True)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        stealth(driver,
              languages=["en-US", "en"],
              vendor="Google Inc.",
              platform="Win32",
              webgl_vendor="Intel Inc.",
              renderer="Intel Iris OpenGL Engine",
              fix_hairline=True,
              )
        
        print("Navigating to Google.com to set the correct domain for cookies...")
        driver.get("https://www.google.com")
        time.sleep(2)

        print("Loading hardcoded cookies...")
        cookies = json.loads(HARDCODED_COOKIES)
        
        for cookie in cookies:
            if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                cookie['sameSite'] = 'Lax'
            driver.add_cookie(cookie)
        
        print("Cookies loaded. Refreshing the page to apply the login session...")
        driver.refresh()
        time.sleep(3)

        print(f"Login should be applied. Navigating to the Google Meet URL: {meet_url}")
        driver.get(meet_url)

        wait = WebDriverWait(driver, 30)

        print("Waiting for main page content to load...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'c-wiz')))
        print("Main content loaded.")

        print("Waiting for microphone button...")
        mic_off_button_xpath = '//*[@id="yDmH0d"]/c-wiz/div/div/div[25]/div[3]/div/div[2]/div[4]/div/div/div[1]/div[1]/div/div[5]/div[1]/div/div/div[1]/span/span'
        mic_off_button = wait.until(EC.element_to_be_clickable((By.XPATH, mic_off_button_xpath)))
        mic_off_button.click()
        print("Clicked microphone button.")

        print("Waiting for camera button...")
        cam_off_button_xpath = '//*[@id="yDmH0d"]/c-wiz/div/div/div[25]/div[3]/div/div[2]/div[4]/div/div/div[1]/div[1]/div/div[5]/div[2]/div/div[1]/span/span'
        cam_off_button = wait.until(EC.element_to_be_clickable((By.XPATH, cam_off_button_xpath)))
        cam_off_button.click()
        print("Clicked camera button.")

        print("Waiting for 'Join now' button...")
        join_now_button_xpath = '//*[@id="yDmH0d"]/c-wiz/div/div/div[25]/div[3]/div/div[2]/div[4]/div/div/div[2]/div[1]/div[2]/div[2]/div[1]/div[1]/span/span'
        join_now_button = wait.until(EC.element_to_be_clickable((By.XPATH, join_now_button_xpath)))
        join_now_button.click()
        print("Clicked 'Join now' button.")

        print("--- [SUCCESS] Successfully joined the Google Meet. ---")
        return "Successfully joined the Google Meet."
    except Exception as e:
        print(f"\n--- [ERROR] An error occurred in join_gmeet: {e} ---")
        return f"An error occurred: {e}"
    finally:
        print("--- [G-Meet Job Finished] ---")
        pass

class GMeetInput(BaseModel):
    meet_url: str = Field(description="The URL of the Google Meet to join.")

gmeet_tool = StructuredTool.from_function(
    func=join_gmeet,
    name="join_gmeet",
    description="Joins a Google Meet by loading hardcoded cookies.",
    args_schema=GMeetInput,
)
