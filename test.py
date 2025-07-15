from selenium import webdriver
from selenium.webdriver.common.by import By
driver = webdriver.Chrome()
driver.get("https://www.ccdi.gov.cn/scdcn/sggb/zjsc/")
html_content = driver.page_source
print(html_content)