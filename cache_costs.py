import gzip
import logging
import time
import re
import argparse
import sys

import yaml
from seleniumwire import webdriver
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(levelname)s:%(asctime)s:%(name)s:%(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

parser = argparse.ArgumentParser(description="Get usage data from vattenfall.nl using selenium.")
parser.add_argument('-v', '--verbose', action='count')
args = parser.parse_args()

if not args.verbose:
    logger.setLevel(logging.WARNING)
elif args.verbose == 1:
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.DEBUG)

implicit_wait = 20

login1_class_name = "vf-header__top_login"
login2_xpath = "//iam-login-form/div[1]/form/div/button"
cookie_id = "acceptBtn"
username_field_id = "username"
password_field_id = "login_password"
verbruik_xpath = "//vfc-navigation-header/div/div[3]/div/div/div[2]/ul/li[3]/a"
kosten_xpath = "//vf-consumption-tabs-desktop/div/vfc-tab-group/div/div[3]/span[2]"

api_url_cost_filter = lambda x: 'api.vattenfall' in x.url and '/1/?Interval' in x.url

datefrom_regex = r"(DateFrom=)(.*)(&)"

with open('account.yml', 'r') as f:
    account = yaml.load(f, yaml.Loader)
    startofsupply = account['startofsupply']
    if startofsupply == '1970-12-31':
        logger.error(f"'startofsupply:' not set")
        sys.exit(-1)
    logger.info(f'startofsupply = {startofsupply}')
    
    username = account['username']
    if username == 'your@ema.il':
        logger.error(f"'username:' not set")
        sys.exit(-1)
    logger.info(f'username = {username}')

    password = account['password']
    if password == 'hunter123':
        logger.error(f"'password:' not set")
        sys.exit(-1)

def datefrom_interceptor(request):
    if '1/?Interval=' in request.url and 'GetAggregatedResults=false' in request.url:
        # print(request.url)
        # print(request.headers)
        logger.info(f'Fixing date to startofsupply={startofsupply}')
        request.url = re.sub(datefrom_regex, f"\\g<1>{startofsupply}\\g<3>", request.url)
        # request.headers['marker'] = 'x'
        # print(request.url)

def datadump_interceptor(request, response):
    if '1/?Interval=' in request.url and 'GetAggregatedResults=false' in request.url and startofsupply in request.url:
        logger.info('Capturing relevant data')
        data_gz = request.response.body
        assert request.response.status_code == 200
        assert dict(request.response.headers)['content-type'] == 'application/json; charset=utf-8'
        assert dict(request.response.headers)['content-encoding'] == 'gzip'
        data_json_s = gzip.decompress(data_gz)
        with open(f'.cached_costs_{int(time.time())}.json', 'wb') as cost_cache_f:
            cost_cache_f.write(data_json_s)

logger.info("Opening webdriver")
driver = webdriver.Firefox()
logger.info("Opening setting interceptors")
driver.request_interceptor = datefrom_interceptor
driver.response_interceptor = datadump_interceptor

try:
    driver.get("http://www.vattenfall.nl")
    logger.info(f'implicit_wait = {implicit_wait}s')
    driver.implicitly_wait(implicit_wait)

    elem = driver.find_element(By.ID, cookie_id)
    assert elem.text == 'Ja, ik accepteer cookies'
    elem.click()

    elem = driver.find_element(By.CLASS_NAME, login1_class_name)
    assert elem.text == 'Inloggen'
    elem.click()

    elem = driver.find_element(By.ID, username_field_id)
    elem.clear()
    elem.send_keys(username)

    elem = driver.find_element(By.ID, password_field_id)
    elem.clear()
    elem.send_keys(password)

    elem = driver.find_element(By.XPATH, login2_xpath)
    assert elem.text == 'Inloggen'
    elem.click()

    logger.info('Successfully logged in')

    elem = driver.find_element(By.XPATH, verbruik_xpath)
    assert elem.text == 'Verbruik'
    elem.click()

    elem = driver.find_element(By.XPATH, kosten_xpath)
    assert elem.text == 'Kosten'
    elem.click()

    # The rest is handled by interceptors, give them some time to complete
    # TODO: wait in a better way
    logger.info('Giving time for the right api call to finish')
    time.sleep(4)
    logger.info(f'len(driver.requests) = {len(driver.requests)}')
    input("exit?")
finally:
    pass
    driver.close()
