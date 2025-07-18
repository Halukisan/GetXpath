import re
import requests
import time
from queue import Queue
from threading import Lock
from lxml import html
from yaml import SafeLoader
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor
from webdriver_pool import WebDriverPool

# 创建全局的WebDriver池
driver_pool = WebDriverPool(pool_size=3)  # 根据机器性能调整池大小

def get_html_content(url):
    """获取网页HTML内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        return None

def get_html_content_Selenium(url, max_retries=3):
    """使用 Selenium 获取页面内容"""
    for attempt in range(max_retries):
        driver = None
        try:
            driver = driver_pool.get_driver()
            driver.set_page_load_timeout(180)
            driver.set_script_timeout(180)
            
            driver.get(url)
            time.sleep(5)
            
            html_content = driver.page_source
            driver_pool.return_driver(driver)
            return html_content
            
        except Exception as e:
            print(f"获取页面失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if driver:
                driver_pool.return_driver(driver)
            
            if attempt == max_retries - 1:
                print("所有重试都失败，尝试使用备用方法")
                return get_html_content(url)
                
            time.sleep(5)
    
    return None
def find_list_container(page_tree):
    """使用分层搜索策略查找最优列表容器，改进目标列表识别"""
    # 定义多种可能的列表项选择器
    list_selectors = [
        "//li",
        "//tr",
        "//article",
        "//div[contains(@class, 'item')]",
        "//div[contains(@class, 'list')]",
        "//ul//li",
        "//ol//li",
        "//table//tr",
        "//section//ul[contains(@class, 'item')]",
        "//section//ul[contains(@class, 'list')]",
        "//section//div[contains(@class, 'list')]",
        "//section//div[contains(@class, 'item')]"
    ]
    
    def count_list_items(element):
        """统计元素内的列表项数量"""
        items = element.xpath(
            ".//li | .//tr | .//article | "
            ".//div[contains(@class, 'item')]"
        )
        return len(items)
    
    def calculate_container_score(container):
        """计算容器作为目标列表的得分"""
        score = 0
        
        # 1. 检查是否包含时间字符串（目标列表特征）
        text_content = container.text_content().lower()
        # 一部分事项列表都有时间字符串
        time_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{4}年\d{1,2}月\d{1,2}日',  
            r'\d{4}/\d{1,2}/\d{1,2}',  # YYYY/MM/DD
            r'年', r'月', r'日',  
            r'发布时间', r'更新日期'
        ]
        
        for pattern in time_patterns:
            if re.search(pattern, text_content):
                score += 10  # 发现时间特征加分
        
        # 2. 检查平均文本长度（目标列表通常有较长文本）
        items = container.xpath(".//*[self::li or self::tr or self::article or self::div[contains(@class, 'item')]]")
        if items:
            total_length = sum(len(item.text_content().strip()) for item in items)
            avg_length = total_length / len(items)
            if avg_length > 50:  # 平均文本长度超过50字符
                score += 8
            elif avg_length > 30:
                score += 5
            elif avg_length > 15:
                score += 2
        
        # 3. 检查是否包含导航特征（导航栏通常有这些特征）
        xpath = generate_xpath(container).lower()
        if 'nav' in xpath or 'menu' in xpath or 'sidebar' in xpath:
            score -= 15  # 导航特征减分
            
        # 4. 检查类名和ID特征
        classes = container.get('class', '').lower()
        elem_id = container.get('id', '').lower()
        
        # 负面特征（导航/页眉/页脚）
        negative_indicators = ['nav', 'menu', 'sidebar', 'header', 'footer', 'topbar']
        for indicator in negative_indicators:
            if indicator in classes or indicator in elem_id:
                score -= 12
        
        # 正面特征（内容/列表/主体）
        positive_indicators = ['content', 'main', 'list', 'result', 'item', 'news', 'article']
        for indicator in positive_indicators:
            if indicator in classes or indicator in elem_id:
                score += 8
        
        return score
    
    # 第一层：找到所有可能的列表项
    all_items = []
    for selector in list_selectors:
        items = page_tree.xpath(selector)
        all_items.extend(items)
    
    if not all_items:
        return None
    
    # 按照父元素分组，找到包含列表项的父元素
    parent_counts = {}
    for item in all_items:
        parent = item.getparent()
        if parent is not None:
            if parent not in parent_counts:
                parent_counts[parent] = 0
            parent_counts[parent] += 1
    
    if not parent_counts:
        return None
    
    # 筛选候选容器：至少包含3个列表项
    candidate_containers = [(parent, count) for parent, count in parent_counts.items() if count >= 3]
    
    # 如果没有符合条件的容器，返回包含最多列表项的容器
    if not candidate_containers:
        return max(parent_counts.items(), key=lambda x: x[1])[0]
    
    # 对候选容器进行评分并排序
    scored_containers = []
    for container, count in candidate_containers:
        score = calculate_container_score(container)
        scored_containers.append((container, score, count))
    
    # 按分数排序（分数相同则按列表项数量排序）
    scored_containers.sort(key=lambda x: (x[1], x[2]), reverse=True)
    
    # 选择得分最高的容器作为初始候选
    best_container = scored_containers[0][0]
    max_items = parent_counts[best_container]
    
    # 逐层向上搜索优化容器
    current_container = best_container
    while True:
        parent = current_container.getparent()
        if parent is None or parent.tag == 'html':
            break
            
        # 计算父元素中的列表项数量
        parent_items = count_list_items(parent)
        
        # 如果父元素的列表项数量显著增加，说明范围太大，保持当前容器
        if parent_items > max_items * 1.5:
            break
            
        # 检查父元素是否更适合作为容器
        parent_score = calculate_container_score(parent)
        current_score = calculate_container_score(current_container)
        
        # 如果父元素得分更高，则升级为当前容器
        if parent_score > current_score:
            current_container = parent
            max_items = parent_items
        else:
            break
            
        # 如果当前容器只包含很少的直接子列表项，说明已经到达最优层级
        direct_items = len(current_container.xpath(
            "./li | ./tr | ./article | ./div[contains(@class, 'item')]"
        ))
        if direct_items < 3:
            break
    
    return current_container
def generate_xpath(element):
    """从元素生成XPath表达式"""
    if not element:
        return None

    tag = element.tag

    # 1. 优先使用ID（如果存在）
    if element.get('id'):
        return f"//{tag}[@id='{element.get('id')}']"

    # 2. 使用最长类名（如果存在）
    classes = element.get('class')
    if classes:
        class_list = [cls.strip() for cls in classes.split() if cls.strip()]
        if class_list:
            # 选择最长的类名
            longest_class = max(class_list, key=len)
            return f"//{tag}[contains(concat(' ', normalize-space(@class), ' '), ' {longest_class} ')]"

    # 3. 使用其他属性（如 aria-label 等）
    for attr in ['aria-label', 'role', 'data-testid', 'data-role']:
        attr_value = element.get(attr)
        if attr_value:
            return f"//{tag}[@{attr}='{attr_value}']"

    # 4. 尝试找到最近的有标识符的祖先，生成相对路径
    def find_closest_identifier(el):
        parent = el.getparent()
        while parent is not None and parent.tag != 'html':
            # 优先使用 ID
            if parent.get('id'):
                return parent
            # 使用类名
            parent_classes = parent.get('class')
            if parent_classes:
                parent_class_list = [cls.strip() for cls in parent_classes.split() if cls.strip()]
                if parent_class_list:
                    return parent
            parent = parent.getparent()
        return None

    ancestor = find_closest_identifier(element)
    if ancestor is not None:
        # 生成祖先的 XPath
        ancestor_xpath = generate_xpath(ancestor)
        # 生成从祖先到当前元素的相对路径
        def generate_relative_path(ancestor_el, target_el):
            path = []
            current = target_el
            while current is not None and current != ancestor_el:
                index = 1
                sibling = current.getprevious()
                while sibling is not None:
                    if sibling.tag == current.tag:
                        index += 1
                    sibling = sibling.getprevious()
                path.insert(0, f"{current.tag}[{index}]")
                current = current.getparent()
            return '/' + '/'.join(path)

        relative_path = generate_relative_path(ancestor, element)
        return f"{ancestor_xpath}{relative_path}"

    # 5. 基于位置的 XPath（最后手段）
    path = []
    current = element
    while current is not None and current.tag != 'html':
        index = 1
        sibling = current.getprevious()
        while sibling is not None:
            if sibling.tag == current.tag:
                index += 1
            sibling = sibling.getprevious()
        path.insert(0, f"{current.tag}[{index}]")
        current = current.getparent()

    return '/' + '/'.join(path)

def validate_xpath(xpath, html_content):
    """验证XPath是否返回有效结果"""
    try:
        tree = html.fromstring(html_content)
        results = tree.xpath(xpath)
        
        if not results:
            return False, "未找到元素"
        
        container = results[0]
        list_items = container.xpath(".//li | .//tr | .//article | .//div[contains(concat(' ', normalize-space(@class), ' '), ' item ')]")

        
        if len(list_items) >= 3:
            return True, f"找到 {len(list_items)} 个列表项"
        
        return False, f"仅找到 {len(list_items)} 个列表项（需要至少3个）"
    except Exception as e:
        return False, f"XPath执行错误: {str(e)}"


def get_robust_xpath(element):
    """生成更健壮的XPath表达式，处理空格和动态文本"""
    # 获取基本属性
    tag = element.tag
    raw_text = element.text.strip() if element.text else ""
    
    # 清理文本：移除多余空格和不可见字符
    cleaned_text = re.sub(r'\s+', ' ', raw_text).strip()
    
    # 获取唯一标识属性
    attributes = []
    for attr in ['id', 'class', 'href', 'src', 'name', 'type', 'value']:
        attr_val = element.attr(attr)
        if attr_val:
            # 简化class值（通常有多个类名）
            if attr == 'class':
                # 取第一个有意义的class
                first_class = attr_val.split()[0] if attr_val else ""
                if first_class and len(first_class) > 2:  # 忽略太短的class
                    attributes.append(f"contains(@class, '{first_class}')")
            else:
                # 截取部分属性值避免过长
                attr_val_short = attr_val[:30] + '...' if len(attr_val) > 30 else attr_val
                attributes.append(f"contains(@{attr}, '{attr_val_short}')")
    
    # 构建XPath选项
    options = []
    
    # 选项1：使用清理后的文本 + contains()
    if cleaned_text:
        # 取文本的前5个和后5个字符（避免中间变化）
        text_part = cleaned_text
        if len(cleaned_text) > 10:
            text_part = f"{cleaned_text[:5]}...{cleaned_text[-5:]}"
        options.append(f"contains(text(), '{text_part}')")

    
    # 组合最终表达式
    if options:
        conditions = ' or '.join([f"({opt})" for opt in options])
        return f"//{tag}[{conditions}]"
    else:
        # 最后手段：仅使用标签
        return f"//{tag}"
from DrissionPage import ChromiumPage
import json
def process_name(name_str):
    """处理name字段：去除js+智能分割标签"""
    # 1. 去除所有'js'子串（全局替换）
    cleaned_name = name_str.replace('js', '')
    
    # 2. 智能选择分隔符（优先>，其次-）
    separator = '>' if '>' in cleaned_name else '-'
    
    # 3. 分割标签并过滤空值
    return [tag.strip() for tag in cleaned_name.split(separator) if tag.strip()]

def get_html_content_Drission(name, url):
    tab_list = process_name(name)
    if not tab_list:
        print("警告：未解析出有效标签")
        return {"html": "", "xpathList4Click": []}

    page = ChromiumPage()
    xpathList4Click = []
    
    try:
        page.get(url)
        
        for i, tab_text in enumerate(tab_list):
            print(f"正在处理标签: {tab_text}")

            xpath_strategies = [
                f'xpath: //body//*[contains(text(),"{tab_text}") and name()!="script"]',
                f'xpath: //*[normalize-space()="{tab_text}"]',  # 完全匹配文本（忽略首尾空格）
                f'xpath: //*[contains(text(), "{tab_text}")]',  # 部分匹配文本
                f'xpath: //a[normalize-space()="{tab_text}"]',  # 限定在<a>标签
                f'xpath: //button[normalize-space()="{tab_text}"]',  # 限定在<button>标签
                f'xpath: //*[@title="{tab_text}"]',  # 通过title属性匹配
                f'xpath: //*[@data-name="{tab_text}"]',  # 通过data属性匹配
            ]     
            tab_element = None
            for strategy in xpath_strategies:
                if not tab_element:
                    try:
                        tab_element = page.ele(strategy, timeout=5)
                        if tab_element:
                            print(f"使用策略找到元素: {strategy}")
                            break
                    except Exception:
                        continue
            
            if tab_element:
                # 获取稳健XPath并点击
                tab_xpath = get_robust_xpath(tab_element)
                xpathList4Click.append(tab_xpath)
                tab_element.click(by_js=True)
                print(f"已点击({i+1}/{len(tab_list)}): {tab_text} - XPath: {tab_xpath}")
                
                # 等待加载
                page.wait.load_start()
                page.wait(3)  # 稳定等待
            else:
                print(f"⚠️ 未找到标签: '{tab_text}'，跳过后续操作")
                break

        # 获取渲染后的HTML
        rendered_html = page.html
        
        return  rendered_html,xpathList4Click
        
    except Exception as e:
        print(f"操作出错: {str(e)}")
        
        return html,xpathList4Click
    
    finally:
        page.quit()
        print("浏览器已关闭")

# def get_robust_xpath(element):
#     """生成更健壮的XPath表达式，处理空格和动态文本"""
#     # 获取基本属性
#     tag = element.tag
#     raw_text = element.text.strip() if element.text else ""
    
#     # 清理文本：移除多余空格和不可见字符
#     cleaned_text = re.sub(r'\s+', ' ', raw_text).strip()
    
#     # 获取唯一标识属性
#     attributes = []
#     for attr in ['id', 'class', 'href', 'src', 'name', 'type', 'value']:
#         attr_val = element.attr(attr)
#         if attr_val:
#             # 简化class值（通常有多个类名）
#             if attr == 'class':
#                 # 取第一个有意义的class
#                 first_class = attr_val.split()[0] if attr_val else ""
#                 if first_class and len(first_class) > 2:  # 忽略太短的class
#                     attributes.append(f"contains(@class, '{first_class}')")
#             else:
#                 # 截取部分属性值避免过长
#                 attr_val_short = attr_val[:30] + '...' if len(attr_val) > 30 else attr_val
#                 attributes.append(f"contains(@{attr}, '{attr_val_short}')")
    
#     # 构建XPath选项
#     options = []
    
#     # 选项1：使用清理后的文本 + contains()
#     if cleaned_text:
#         # 取文本的前5个和后5个字符（避免中间变化）
#         text_part = cleaned_text
#         if len(cleaned_text) > 10:
#             text_part = f"{cleaned_text[:5]}...{cleaned_text[-5:]}"
#         options.append(f"contains(text(), '{text_part}')")

    
#     # 组合最终表达式
#     if options:
#         conditions = ' or '.join([f"({opt})" for opt in options])
#         return f"//{tag}[{conditions}]"
#     else:
#         # 最后手段：仅使用标签
#         return f"//{tag}"

def process_entry(entry, max_retries=3):
    """处理单个条目"""
    url = entry['url']
    name = entry['name']
    xpathList4Click = ""
    print(f"\n处理: {entry['name']}")
    print(f"URL: {url}")
    if name.endswith('js'):
        print("JS页面")
        html_content,xpathList4Click = get_html_content_Drission(name,url)
    else :
        print("非JS页面")
        # 有100%可以获取的方法就不要换成可能出风险的方法，慢一点就慢一点，准确率最重要
        html_content = get_html_content_Selenium(url)

    # html_content = get_html_content(url)
    
    if not html_content:
        print("\nHtml content获取失败")
        return {**entry, 'xpath': None, 'status': 'failed'}
        
    best_xpath = None
    validation_result = ""
    candidate_xpath = None  # 添加初始化

    for attempt in range(1, max_retries + 1):
        print(f"\n尝试 #{attempt}")
        
        tree = html.fromstring(html_content)
        
        container = find_list_container(tree)
        
        if not container:
            print("未找到有效的列表容器")
            continue
        
        candidate_xpath = generate_xpath(container)
        if not candidate_xpath:
            print("无法生成XPath")
            time.sleep(1)
            continue

        print(f"XPath: {candidate_xpath}")
        is_valid, validation_msg = validate_xpath(candidate_xpath, html_content)
        print(f"XPath候选: {candidate_xpath}")
        print(f"验证结果: {validation_msg}")
        
        if is_valid:
            best_xpath = candidate_xpath
            validation_result = validation_msg
            break
        elif attempt == max_retries:
            # 最后一次尝试，使用最佳候选（即使不完美）
            best_xpath = candidate_xpath
            validation_result = f"最终选择: {validation_msg}"

    if best_xpath:
        if xpathList4Click:
            print(f"✓ 最终XPath: {best_xpath} (点击列表: {xpathList4Click})")
            return {**entry, 'xpath': best_xpath, 'status': 'success', 'xpathList4Click': xpathList4Click}
        else :
            print(f"✓ 最终XPath: {best_xpath}")
            return {**entry, 'xpath': best_xpath, 'status': 'success', 'xpathList4Click': None}
    
    print("✗ 未能找到有效XPath")
    return {**entry, 'xpath': None, 'status': 'failed','xpathList4Click': None}

def parse_input_file(input_file):
    """解析输入文件"""
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 使用正则表达式匹配每个条目
    pattern = r'name:\s*(.*?)\s*url:\s*(https?://\S+)\s*'
    matches = re.findall(pattern, content)
    
    entries = []
    for match in matches:
        entries.append({
            'name': match[0],
            'url': match[1]
        })
    
    return entries

def write_output_file(results, output_file):
    """写入输出文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
            # 只保留原始字段和xpath
            output_data = {
                'name': result['name'],
                'url': result['url'],
                'xpath': result.get('xpath', '')  # 如果没有xpath则为空字符串
            }
            if result.get('xpathList4Click'):
                output_data['xpathList4Click'] = result['xpathList4Click']
            # 写入条目
            f.write("---\n")  # 添加分隔符
            f.write(f"name: {output_data['name']}\n")
            f.write(f"url: {output_data['url']}\n")
            f.write(f"xpath: \"{output_data['xpath']}\"\n")
            # 正确写入xpathList4Click作为YAML列表
            if 'xpathList4Click' in output_data and output_data['xpathList4Click']:
                f.write("xpathList4Click:\n")
                for xpath in output_data['xpathList4Click']:
                    # 转义XPath中的特殊字符
                    safe_xpath = xpath.replace('"', '\\"').replace('\n', '\\n')
                    f.write(f"  - \"{safe_xpath}\"\n")
            else:
                f.write("xpathList4Click: []\n")
            

def process_entries_parallel(entries, max_workers=1):
    """并行处理多个条目"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_entry, entries))
    return results

def process_yml_file(input_file, output_file):
    """处理YML文件"""
    entries = parse_input_file(input_file)
    total = len(entries)
    
    if total == 0:
        print("未找到有效条目")
        return
    
    print(f"找到 {total} 个待处理条目")
    
    # 使用并行处理
    results = process_entries_parallel(entries)
    
    # 写入结果
    write_output_file(results, output_file)
    
    # 生成统计报告
    success_count = sum(1 for r in results if r.get('status') == 'success')
    failure_count = total - success_count
    
    print(f"\n处理完成: {success_count} 成功, {failure_count} 失败")
    print(f"结果已保存至: {output_file}")

import os
import glob
if __name__ == "__main__":
    try:
        input_file = "test.yml"    # 输入文件路径
        output_file = "testout.yml"  # 输出文件路径
        
        process_yml_file(input_file, output_file)


        # input_folder = "waitprocess"
        # output_folder = "processed"  
        
        # if not os.path.exists(output_folder):
        #     os.makedirs(output_folder)
        
        # files = glob.glob(os.path.join(input_folder, "*.yml"))
        
        # for input_file in files:
        #     base_name = os.path.basename(input_file)  
        #     output_file = os.path.join(output_folder, base_name)
        #     process_yml_file(input_file, output_file)
    finally:
        driver_pool.close_all()




# 一个页面中，存在k个列表，假定k=3，有三个列表，列表1为导航栏，里面有8个列表项，列表2为侧边栏，里面有5个列表项，列表3是事项列表，里面有7个列表项，
# 此时，我的代码会把列表1作为目标获取，但实际情况应该是列表3才是正确的，这怎么办呢，
# 目前对于目标列表3，可能存在以下特点：里面往往存在时间字符串，并且有些页面中的文字的长度是大于列表1和列表2的。
# 除此之外，对于列表1，也有以下特点：当我们误获取这个列表1的时候，会去处理组装他的xpath，这个xpath里面往往是存在nav三个字母的，
# 在我的观察下，大部分情况中，只要xpath里面包含nav，那就很大可能说明获取失败了，没有获取到列表3，而是获取到了列表1