import json
import time
import configparser as conf
import requests as r

import undetected_chromedriver as uc

from selenium.webdriver.common.by import By
from datetime import datetime


class AvitoParser:
    # check_interval is count of minutes between refreshing page
    # total_cscript willheck_time - how long  work in hours
    def __init__(self, price: int, url: str, items: list, browser_ver: int = None,
                 check_interval: int = 3,
                 total_check_time: int = 5):
        self.url = url
        self.items = items
        self.browser_ver = browser_ver
        self.data = []
        self.price_threshold = price
        self.mins_to_check = ['минута', 'минуты', 'минут']
        self.hours_to_check = ['час', 'часа', 'часов']
        self.check_interval = check_interval
        self.total_check_time = total_check_time
        conf_reader = conf.ConfigParser()
        conf_reader.read('config.ini')
        self.TOKEN = conf_reader["TELEGRAM_BOT"]["token"]
        self.CHAT_ID = conf_reader["TELEGRAM_BOT"]["chat_id"]

    def __set_up(self):
        self.driver = uc.Chrome(version_main=self.browser_ver)

    def __get_url(self):
        self.driver.get(self.url)

    def __paginator(self):
        iteration_counter = 1
        start_time = time.time()
        while time.time() < start_time + self.total_check_time * 3600:
            self.__parse_page()
            if self.data:
                self.__save_json()
                for item in self.data:
                    self.__send_mes(item['url'])
                print("Apartment wrote to the file")
            else:
                self.__send_mes('There were not apartments')
                print("Apartments were not found")
            print(f"iteration num - {iteration_counter}, iteration time - {datetime.now().strftime('%m-%d %H:%M:%S')}")
            iteration_counter += 1
            time.sleep(self.check_interval * 60)
            self.driver.refresh()  # есть ещё driver.navigate().refresh() попробую если с этим будут проблемы.
        print("Successfully parsed pages")
        self.driver.quit()

    def __send_mes(self, mes):
        url = f"https://api.telegram.org/bot{self.TOKEN}/sendMessage?chat_id={self.CHAT_ID}&text={mes}"
        r.get(url)

    def test(self):
        self.__send_mes("test message")

    def __parse_page(self):
        sale_ads = self.driver.find_elements(By.CSS_SELECTOR, "[data-marker='item']")
        for ad in sale_ads:
            name = ad.find_element(By.CSS_SELECTOR, "[itemprop='name']").text
            url = ad.find_element(By.CSS_SELECTOR, "[data-marker='item-title']").get_attribute("href")
            price = ad.find_element(By.CSS_SELECTOR, "[itemprop='price']").get_attribute("content")
            published_time = ad.find_element(By.CSS_SELECTOR, "[data-marker='item-date']").text

            print("Info about post")
            print(name)
            print(url)
            print(price)
            print(published_time)
            print("end of info block")


            self.data.append({
                'name': name,
                'url': url,
                'price': price,
                'published_time': published_time
            })
            print(name, url, price, published_time)

    # def __is_ad_appropriate(self, price, published_time) -> bool:
        # if any([word in published_time for word in self.hours_to_check]):
            # return False
        # if int(published_time.split(' ')[0]) <= self.check_interval and int(price) <= self.price_threshold:
            # return True

    def __save_json(self):
        with open("data.json", "a", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=4)

        self.data.clear()

    def parse(self):
        self.__set_up()
        self.__get_url()
        self.__paginator()


if __name__ == '__main__':
    AvitoParser(
        url="https://www.avito.ru/voronezh/kvartiry/sdam/na_dlitelnyy_srok-ASgBAgICAkSSA8gQ8AeQUg?cd=1&context=H4sIAAAAAAAA_wEjANz_YToxOntzOjg6ImZyb21QYWdlIjtzOjc6ImNhdGFsb2ciO312FITcIwAAAA&f=ASgBAgECAkSSA8gQ8AeQUgFFxpoMFXsiZnJvbSI6MCwidG8iOjI1MDAwfQ&s=104",
        items=['adf'],
        browser_ver=136,
        check_interval=10,
        price=20000).parse()
    # print(len("1111111111111111111111111111111111111111"))
